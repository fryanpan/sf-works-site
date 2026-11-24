#!/usr/bin/env python3
"""The data quality checks each transportation source must pass after every fetch, per source step.

    pipeline/transportation-quality.py                 # check every source's data on disk now
    pipeline/transportation-quality.py mirror:bos socrata
    pipeline/transportation-quality.py --inventory     # one row per source: marker, re-read, checks
    pipeline/transportation-quality.py --inventory --check   # exit 1 if a source step is missing or a row says none

pipeline/transportation-update.py runs these right after each source step
(pipeline/README.md, rule 2). Before the step it snapshots every
path the step can write (SPECS[step].paths); after it, it runs the step's
checks against the new data, with the snapshot as the previous data for the
row-count bound. A failing check puts the snapshot back, records the failure
in data/pipeline-state/sources.json, skips every build step, and exits 1
naming the check. The checks themselves are the five in lib/quality.py.

Each spec also says what the source's change marker is and what an update
re-reads, so --inventory prints the table docs/product/transportation-pipeline.md
carries. Floors are set a little under the counts on 2026-09-28, so they catch
a source that has emptied rather than one that has shrunk; the shrink is the
max_drop bound against the previous data.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import calendar
import collections
import csv
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.quality import Each, Join, Result, Table, json_rows, read_json, run  # noqa: E402
from lib import mirror as mirror_lib  # noqa: E402

# DataSF datasets the transportation scripts read through lib/sfdata.py;
# pipeline/transportation-update.py imports this list.
SOCRATA = ["3i4a-hu95", "3psu-pn9h", "5wbp-dwzt", "78va-8dhi", "7e7j-59qk", "9ivs-nf5y", "abhw-ffzx",
           "bp3t-bd4t", "btxj-k9uh", "e6tr-sxwg", "gtr9-ntp6", "i28k-bkz6", "ygmz-vaxd"]

# Per dataset: the key that is unique in a whole-row query, the fields every
# row carries (with the share allowed to lack one), and date fields' ranges.
# Measured on the cached queries of 2026-09-28.
SOCRATA_RULES = {
    "3psu-pn9h": dict(key="cnn", required=["cnn"]),
    "5wbp-dwzt": dict(key="id", required=["id", "cnn"],
                      dates={"modifieddate": ("2000-01-01", "+2")}),
    "78va-8dhi": dict(required=["cnn"], dates={"pci_change_date": ("1900-01-01", "+2")}),
    # Schools: the private K-12 rows the bike history counts; count-only
    # queries carry no cds_code and are skipped by the required check.
    "7e7j-59qk": dict(key="cds_code", required=["cds_code", "latitude", "longitude", "open_date"],
                      dates={"open_date": ("1850-01-01", "+1")}),
    "9ivs-nf5y": dict(key="objectid", required=["cnn"]),
    "abhw-ffzx": dict(required=[("cnn", 0.01)]),
    "bp3t-bd4t": dict(required=[("cnn", 0.10)]),
    "btxj-k9uh": dict(required=["dotmapsid", "cnn"],
                      dates={"start_date": ("1990-01-01", "2080-01-01"), "end_date": ("1990-01-01", "2080-01-01")}),
    # SFUSD elementary attendance areas (2024-25), for lib/school-travel-time.py.
    "e6tr-sxwg": dict(key="objectid_1", required=["the_geom", "sch_lng_na"]),
    "i28k-bkz6": dict(key="objectid"),
    "ygmz-vaxd": dict(key="objectid", required=[("cnn", 0.01)]),
    "hkz3-itiu": dict(required=["cnn"]),
    # The full access map's parks (Rec and Park properties) and commercial districts (Planning's zoning map),
    # read by tools/travel/full-map-destinations.py. Measured 2026-10-23: 255 and 10,617 rows.
    "gtr9-ntp6": dict(key="property_id", required=["property_id", "property_name", "propertytype", "acres", "shape"],
                      dates={"last_edited_date": ("2000-01-01", "+2")}),
    "3i4a-hu95": dict(required=["the_geom", "zoning_sim"]),
    # The Street Safety map's crash reads (tools/street-safety/street-safety-crashes.py, which also checks unique keys, allowing the
    # identical repeats DataSF carries, and the victims-to-crashes join before a re-read replaces a held copy).
    "nwes-mmgh": dict(required=["case_id_pkey", "collision_datetime"], dates={"collision_datetime": ("2005-01-01", "+1")}),
    "8gtc-pjc6": dict(required=["case_id_pkey", "party_number_ckey", "collision_datetime"],
                      dates={"collision_datetime": ("2005-01-01", "+1")}),
    "ubvf-ztfx": dict(required=["case_id_pkey", "collision_datetime"], dates={"collision_datetime": ("2005-01-01", "+1")}),
    "dau3-4s8f": dict(required=["unique_id", "collision_datetime"], dates={"collision_datetime": ("2005-01-01", "+1")}),
}
STREET_SAFETY_CRASHES = ("nwes-mmgh", "8gtc-pjc6", "ubvf-ztfx", "dau3-4s8f")   # lib/street_safety_reads.py DATASETS


class Spec(object):
    """One source step: what it writes, how it knows something changed, and its checks.

    `checks(root)` returns the Tables and Joins; it is a function so a source
    with one file per query or per meeting can list them from disk.
    """

    def __init__(self, paths, checks, marker, reread, flag):
        self.paths, self.checks = paths, checks
        self.marker, self.reread, self.flag = marker, reread, flag


def rows_of(rel, *path):
    return json_rows(rel, *path)


def records(source, key, *path):
    """A loader for the records of data/extract/<source>/<key>.json, optionally a list inside record 0."""
    rel = "data/extract/%s/%s.json" % (source, key)

    def load(root):
        d = read_json(root, rel)
        if d is None:
            return None
        r = d["records"]
        for k in path:
            r = r[k]
        return r
    return load


def blob_meta(rel, field="fetched_on"):
    """The one row of a file's read date, so a date check can cover it."""
    def load(root):
        d = read_json(root, rel)
        return None if d is None else [{"read": d.get(field)}]
    return load


def extract_read(source, key):
    return Table("extract:%s/%s.read-date" % (source, key), blob_meta("data/extract/%s/%s.json" % (source, key)),
                 floor=1, max_drop=None, required=["read"], dates={"read": ("2019-01-01", "+1")})


def year(field):
    def f(r):
        v = r.get(field)
        return "%04d-01-01" % v if isinstance(v, int) and v else None
    f.__name__ = field
    return f


# ---- DataSF ---------------------------------------------------------------------

def socrata_checks(fxfs, cache="data/socrata-cache"):
    def checks(root):
        out = []
        for fxf in fxfs:
            rule = SOCRATA_RULES.get(fxf, {})
            for p in sorted(glob.glob(os.path.join(root, cache, "%s-*.json" % fxf))):
                rel = os.path.relpath(p, root)
                name = "socrata:" + os.path.basename(p)[:-5]
                blob = read_json(root, rel)
                sample = set(k for r in blob["rows"][:200] for k in r)
                full = rule.get("key") in sample if rule.get("key") else True
                out.append(Table(name, rows_of(rel, "rows"), floor=1, max_drop=0.30, max_growth=2.0,
                                 key=rule.get("key") if full else None,
                                 required=[r for r in rule.get("required", [])
                                           if (r[0] if isinstance(r, tuple) else r) in sample],
                                 dates={f: b for f, b in rule.get("dates", {}).items() if f in sample}))
                out.append(Table(name + ".read-date", blob_meta(rel), max_drop=None, required=["read"],
                                 dates={"read": ("2019-01-01", "+1")}))
        return out
    return checks


def site_socrata_checks(root):
    out = []
    for p in sorted(glob.glob(os.path.join(root, ".cache", "site-socrata", "*.json"))):
        rel = os.path.relpath(p, root)
        fxf = os.path.basename(p)[:-5]
        rule = SOCRATA_RULES.get(fxf, {})
        out.append(Table("site-socrata:" + fxf, rows_of(rel, "rows"), floor=100, max_drop=0.10,
                         max_growth=1.0, key=rule.get("key"), required=rule.get("required", []),
                         dates=rule.get("dates")))
        out.append(Table("site-socrata:%s.read-date" % fxf, blob_meta(rel, "fetchedOn"), max_drop=None,
                         required=["read"], dates={"read": ("2019-01-01", "+1")}))
    return out


# ---- extracts -------------------------------------------------------------------

def extracts_checks(root):
    net = records("sfmta-bikeway", "network")
    geo = records("sfmta-bikeway", "geometry")
    return [
        Table("extract:sfmta-bikeway/network", net, floor=5000, max_drop=0.05,
              key="OBJECTID", required=["OBJECTID", ("CNN", 0.01), ("FACILITY_T", 0.01)],
              dates={year("INSTALL_YR"): ("1960-01-01", "+366")}),
        Table("extract:sfmta-bikeway/geometry", geo, floor=5000, max_drop=0.05, key="oid",
              required=["oid", ("pts", 0.01)]),
        # The geometry is read in its own query and joined to the attributes by
        # OBJECTID; a row in one and not the other is a dropped segment.
        Join("extract:sfmta-bikeway network~geometry",
             left=lambda r: [x["OBJECTID"] for x in net(r)] if net(r) is not None else None,
             right=lambda r: [x["oid"] for x in geo(r)] if geo(r) is not None else None),
        extract_read("sfmta-bikeway", "network"),
        Table("extract:sfmta-bci/scores", records("sfmta-bci", "scores"), floor=14000, max_drop=0.05,
              key="cnn", required=["cnn", "bci"]),
        extract_read("sfmta-bci", "scores"),
        # Four CNNs carry two Slow Street rows (two phases on one block), so
        # the key is the block and its phase and install date.
        Table("extract:slow-streets/segments", records("slow-streets", "segments"), floor=200, max_drop=0.10,
              key=("cnn", "phase", "install_date", "extents"), required=["cnn", "street"],
              dates={"install_date": ("1899-01-01", "+1")}),
        Table("extract:census-blocks/2020", records("census-blocks", "2020"), floor=5900, max_drop=0.0,
              max_growth=0.0, key="geoid", required=["geoid", "pop", "lat", "lon"]),
        Table("extract:libraries/branches", records("libraries", "branches"), floor=25, max_drop=0.10,
              key="facility_id", required=["name", "facility_id", "lat", "lon"]),
        # CPAD's units in San Francisco County (pipeline/sources/cpad-sf.py): 274 in the 2025b release.
        Table("extract:cpad/sf-units", records("cpad", "sf-units"), floor=250, max_drop=0.20, key="unit_id",
              required=["unit_id", "name", "agency", "access", "acres", "geometry"]),
        Each("extract:cpad/presidio", lambda r: None if records("cpad", "sf-units")(r) is None else
             [{"n": sum(1 for x in records("cpad", "sf-units")(r) if x["name"] == "Presidio" and x["acres"] > 1000)}],
             lambda x: None if x["n"] == 1 else "the Presidio unit (over 1,000 acres) is missing",
             "the Presidio is in the extract at over 1,000 acres"),
    ]


# ---- meeting mirrors ------------------------------------------------------------

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def parser_version(script):
    """The PARSER constant a mirror script stamps on each meeting, read from its source."""
    with open(paths.script(script), encoding="utf-8") as fh:
        m = re.search(r"(?m)^PARSER = (\d+)", fh.read())
    return int(m.group(1)) if m else None


def minutes_checks(body, script, floor, undecided=0.05, empty=0.0, consent=re.compile(r"(?i)^\s*consent calendar"),
                   minutes_cache=None):
    """Checks on what a mirror takes from the minutes, beyond the agenda (SFMTA Board, SFPUC).

    Every meeting read with the current parser (a parser change reaches the
    final meetings); the items taken from the minutes above a floor and not
    fallen against the previous data; and every consent calendar of a meeting
    whose minutes are in holds at least one item under it."""
    def files(root):
        out = []
        for p in sorted(glob.glob(os.path.join(root, "data", body, "meetings", "*.json"))):
            with open(p, encoding="utf-8") as fh:
                out.append(json.load(fh))
        return out

    def current(m, want=[]):  # noqa: B006 - read once per run
        if not want:
            want.append(parser_version(script))
        return True if m.get("parser") == want[0] else None
    current.__name__ = "parser_current"

    def minutes_items(root):
        return [dict(it, _date=m["date"]) for m in files(root) for it in m.get("items") or ()
                if it.get("from") == "minutes"]

    def calendars(root):
        out = []
        for m in files(root):
            if not (m.get("sources") or {}).get("minutes"):
                continue
            nos = [str(it.get("no")) for it in m.get("items") or ()]
            for it in m.get("items") or ():
                if consent.match(it.get("title") or ""):
                    no = str(it.get("no"))
                    under = [x for x in nos if x != no and re.match(re.escape(no) + r"[a-z.]", x, re.I)]
                    out.append({"date": m["date"], "no": no, "under": len(under) or None})
        return out

    def items_under(row):
        return row.get("under")
    items_under.__name__ = "items_under_calendar"

    def printed(root):
        """One row per consent calendar whose minutes are in the byte cache: the
        item numbers the minutes print under it, and those the mirror lacks.

        Read from the minutes PDF itself with a header pattern of its own, not
        from the fetcher's reading, so a calendar Granicus indexed in part
        cannot pass because one item is under it."""
        def fold(s):
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:40]
        out = []
        for m in files(root):
            url = (m.get("sources") or {}).get("minutes")
            text = cached_minutes(minutes_cache, url, root) if url else None
            if not text:
                continue
            items = m.get("items") or ()
            nos = {str(it.get("no")) for it in items}
            # The calendars: every point the index names as one, and every
            # heading the minutes print as one, whether the index has it or not.
            cals = {int(it["no"]) for it in items
                    if consent.match(it.get("title") or "") and re.match(r"^\d{1,2}$", str(it.get("no")))}
            cals |= {int(x) for x in re.findall(r"(?m)^\s*(\d{1,2})\.\s+(?:All matters listed hereunder constitute "
                                                  r"a Consent Calendar|CONSENT CALENDAR)", text)}
            for n in sorted(cals):
                start = re.search(r"(?m)^\s*%d\.\s+(?:All matters|CONSENT CALENDAR)" % n, text) \
                    or re.search(r"(?m)^\s*%d\.\s" % n, text)
                if not start:
                    continue
                end = re.compile(r"(?m)^\s*(?:%d\.\s|REGULAR CALENDAR)" % (n + 1)).search(text, start.end())
                seg = text[start.end():end.start() if end else len(text)]
                heads = {}
                for a, b, line in re.findall(r"(?m)^\s*(?:\(%d\.(\d{1,2})\)|%d\.(\d{1,2})\.?)[ \t]+(\S[^\n]*)" % (n, n), seg):
                    heads.setdefault(a or b, line)
                under = [it for it in items if re.match(r"^%d(?:$|[A-Za-z.])" % n, str(it.get("no")))]
                # An item counts as mirrored under its own number, as a
                # lettered form of it ("10.3E"), or as any item under the
                # calendar that opens with the same words (the warrants indexed
                # as "10"). A lettered part ("10.1K") is not its whole item.
                lacking = [k for k, line in sorted(heads.items(), key=lambda x: int(x[0])) if not any(
                    x == "%d.%s" % (n, k) or re.match(r"^%d\.%s[A-Za-z]$" % (n, k), x) for x in nos)
                    and not any(fold(it.get("title")) and fold(it.get("title")) == fold(line) for it in under)]
                out.append({"date": m["date"], "no": str(n), "printed": len(heads),
                            "lacking": ", ".join("%d.%s" % (n, k) for k in lacking) or None})
        return out

    def all_mirrored(row):
        return None if row.get("lacking") else True
    all_mirrored.__name__ = "every_printed_item_mirrored"

    extra = []
    if minutes_cache:
        extra.append(Table("mirror:%s/consent-items-printed" % body, printed, floor=60, max_drop=0.10,
                           key=("date", "no"), required=[all_mirrored]))
    return [
        Table("mirror:%s/parser" % body, files, floor=int(floor * 0.9), max_drop=0.05, required=[current]),
        Table("mirror:%s/minutes-items" % body, minutes_items, floor=floor, max_drop=0.05,
              key=("_date", "no"), required=["title", ("decision", undecided)]),
        Table("mirror:%s/consent-calendars" % body, calendars, floor=1, max_drop=0.10,
              required=[(items_under, empty) if empty else items_under]),
    ] + extra


def cached_minutes(cache, url, root=None):
    """A minutes document's text from the byte cache only (node page, then its PDF), or None.

    Never the network: a check judges what the fetcher had to read. The
    minutes byte cache is outside a step's snapshot, so a snapshot root falls
    back to this checkout's cache; posted minutes do not change."""
    import hashlib
    from lib.fetch import pdf_text

    def raw(u):
        for base in (root, ROOT):
            p = os.path.join(base or ROOT, ".cache", cache, hashlib.sha1(u.encode()).hexdigest())
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    return fh.read()
        return None
    page = raw(url)
    m = re.search(rb'href="(/media/\d+/download[^"]*)"', page or b"")
    return pdf_text(raw("https://www.sfmta.com" + m.group(1).decode())) if m else None


def mirror_checks(body, floor, since="2019-01-01", extra=None):
    idx_rel = "data/%s/index.json" % body

    def files(root):
        out = []
        for p in sorted(glob.glob(os.path.join(root, "data", body, "meetings", "*.json"))):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            d["_file"] = os.path.basename(p)
            out.append(d)
        return out

    def items(root):
        return [dict(it, _date=m["date"], _mid=slug(m.get("id"))) for m in files(root) for it in m.get("items") or ()]

    def item(it):
        return (it["_date"], it["_mid"]) + mirror_lib.item_key(it)

    def status(m):
        return m.get("status") if m.get("status") in ("draft", "final") else None

    def checks(root):
        return [
            Table("mirror:%s/index" % body, rows_of(idx_rel, "meetings"), floor=floor, max_drop=0.05,
                  key=("date", "id"), required=["date", "id", "outcome"],
                  dates={"date": (since, "+400")}),
            Table("mirror:%s/meetings" % body, files, floor=int(floor * 0.9), max_drop=0.05,
                  key=("date", lambda m: slug(m.get("id"))), required=["date", "id", status, "items", "fetched"],
                  dates={"date": ("2019-01-01", "+400"), "fetched": ("2019-01-01", "+1")}),
            # Each agenda point once per meeting: a parser that reads a point
            # twice doubles every discussion count built on the mirror.
            Table("mirror:%s/items" % body, items, floor=floor, max_drop=0.05,
                  key=item, required=[("title", 0.01)]),
            # Every meeting the index counts as mirrored has exactly one file,
            # and every file in the window is in the index.
            Join("mirror:%s index~files" % body,
                 left=lambda r: None if read_json(r, idx_rel) is None else [
                     (m["date"], slug(m["id"])) for m in read_json(r, idx_rel)["meetings"] if m["outcome"] == "mirrored"],
                 right=lambda r: [(m["date"], slug(m["id"])) for m in files(r)
                                  if m["date"] >= (read_json(r, idx_rel) or {}).get("since", since) and m.get("items")]),
        ] + (extra or [])
    return checks


def delegated_checks(root=None):
    """The Public Works Commission's delegated contract reports (tools/meetings/fetch-public-works-commission.py).

    Every report an agenda links is read or listed as unread; each report
    holds contract rows or says it has none; each row carries a ten-digit
    contract ID, a title and what was approved; no row carries an address."""
    rel = "data/public-works-commission/delegated.json"
    reports = rows_of(rel, "reports")

    def rows(r):
        rs = reports(r)
        return None if rs is None else [dict(x, _report=rep["url"], _date=rep["date"]) for rep in rs for x in rep["rows"]]

    def linked(r):
        d = read_json(r, rel)
        if d is None:
            return None
        unread = {u["url"] for u in d.get("unread") or ()}
        return sorted({u for a in d["agendas"] for u in a["reports"]} - unread)

    return [
        Table("pwc-delegated/reports", reports, floor=14, max_drop=0.0, key="url",
              required=["url", "file", "date", "meetings"], dates={"date": ("2024-01-01", "+30")}),
        Table("pwc-delegated/rows", rows, floor=45, max_drop=0.0, key=("_report", "contract", "request"),
              required=["contract", "title", "request", "action"]),
        Each("pwc-delegated/row-shape", rows,
             lambda x: None if (re.match(r"^1\d{9}$", x["contract"]) and len(x["title"]) >= 4
                                and x["action"] in ("award", "modification")
                                and not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", x["title"] + " " + x["request"]))
             else "contract %r, title %r, action %r" % (x.get("contract"), x.get("title"), x.get("action")),
             "a ten-digit contract ID, a title of four letters or more, an award or a modification, no address"),
        Each("pwc-delegated/report-read", reports,
             lambda rep: None if (rep["rows"] or rep.get("empty")) else "no rows and no \"None\" in %s" % rep["file"],
             "each report holds contract rows or says it has none"),
        # Every report an agenda links is read exactly once (or listed as unread).
        Join("pwc-delegated agendas~reports", left=linked,
             right=lambda r: None if reports(r) is None else [x["url"] for x in reports(r)]),
    ]


def mirror_spec(step, body, fetcher_cache, floor, marker, reread, extra=None, paths=()):
    script = {"mirror:bos": "fetch-bos-meetings", "mirror:public-works": "fetch-public-works-commission",
              "mirror:rec-park": "fetch-rec-park-commission", "mirror:sfcta": "fetch-sfcta-board",
              "mirror:sfmta-board": "fetch-sfmta-board", "mirror:sfmta-hearings": "fetch-sfmta-hearings",
              "mirror:sfpuc": "fetch-sfpuc-commission"}[step]
    return Spec(["data/%s/index.json" % body, "data/%s/meetings/*.json" % body, ".cache/%s/**" % fetcher_cache] + list(paths),
                mirror_checks(body, floor, extra=extra), marker, reread,
                "scripts/%s.py (always incremental: a final meeting is never re-read)" % script)


# ---- the rest -------------------------------------------------------------------

def sfmta_projects_checks(root):
    rel = "out/sfmta-projects/projects.json"
    proj = rows_of(rel, "projects")
    return [
        Table("sfmta-projects/projects", proj, floor=200, max_drop=0.05, key="node",
              required=["node", "name", "lastEdited"], dates={"lastEdited": ("2000-01-01", "+1"),
                                                              "created": ("2000-01-01", "+1")}),
        # A failed DataSF mirror query used to leave every project marked as
        # missing from the mirrors; a failed page read leaves it with no prose.
        Table("sfmta-projects/in-datasf-mirror", lambda r: [p for p in (proj(r) or []) if p["inDataSfMirror"]],
              floor=1, max_drop=0.20),
        Table("sfmta-projects/bike-page-text", lambda r: [p for p in (proj(r) or []) if p["bike"] and p["pageText"]],
              floor=1, max_drop=0.10),
        Join("sfmta-projects projects~geojson",
             left=lambda r: None if proj(r) is None else [p["node"] for p in proj(r)],
             right=lambda r: None if read_json(r, "out/sfmta-projects/projects.geojson") is None else sorted(set(
                 str(f["properties"]["node"]) for f in read_json(r, "out/sfmta-projects/projects.geojson")["features"])),
             drop_ok=True),
    ]


def sfmta_pages_checks(root):
    pages = rows_of("out/sfmta-projects/pages.json", "pages")
    bike = records("sfmta-pages", "bike")
    site = records("sfmta-pages", "sitemap")

    def bike_nodes(r):
        d = read_json(r, "out/sfmta-projects/projects.json")
        return None if d is None else [p["node"] for p in d["projects"] if p["bike"] and p["node"]]

    def pages_and_failed(r):
        d = read_json(r, "out/sfmta-projects/pages.json")
        return None if d is None else list(d["pages"]) + [f[0] for f in d["failed"]]
    return [
        Table("sfmta-pages/bike", bike, floor=100, max_drop=0.05, key="node", required=["node", "name", "page"]),
        extract_read("sfmta-pages", "bike"),
        Table("sfmta-pages/sitemap", site, floor=350, max_drop=0.05, key="node", required=["node", "page"]),
        extract_read("sfmta-pages", "sitemap"),
        Table("sfmta-pages/pages.json", pages, floor=350, max_drop=0.05, key="node", required=["node", "page"]),
        # Every bike project on the layer has its page read, or is named as failed.
        Join("sfmta-pages bike-projects~pages", left=bike_nodes, right=pages_and_failed, extra_ok=True),
    ]


def hearings_checks(root):
    rec = "data/extract/sfmta-hearings/since-2010-01-01.json"
    hear = records("sfmta-hearings", "since-2010-01-01", 0, "hearings")
    match = records("sfmta-hearings", "since-2010-01-01", 0, "matches")
    return [
        Table("sfmta-hearings/hearings", hear, floor=130, max_drop=0.05, key=("date", "page"),
              required=["date", "page"], dates={"date": ("2010-01-01", "+60")}),
        Table("sfmta-hearings/matches", match, floor=300, max_drop=0.05, key=("date", "page", "no"),
              required=["date", "page", "no", "head"]),
        extract_read("sfmta-hearings", "since-2010-01-01"),
        # Each match belongs to a listed hearing, and the report carries each
        # hearing and each match of the extract once.
        Join("sfmta-hearings matches~hearings",
             left=lambda r: None if hear(r) is None else [(h["date"], h["page"]) for h in hear(r)],
             right=lambda r: None if match(r) is None else sorted(set((m["date"], m["page"]) for m in match(r))),
             drop_ok=True),
        Join("sfmta-hearings extract~report",
             left=lambda r: None if match(r) is None else [(m["date"], m["page"], m["no"]) for m in match(r)],
             right=lambda r: None if read_json(r, "out/sfmta-hearings/hearings.json") is None else [
                 (m["date"], m["page"], m["no"]) for m in read_json(r, "out/sfmta-hearings/hearings.json")["matches"]]),
    ]


def board_checks(root):
    ag = records("sfmta-board", "since-2019-01-01", 0, "agendas")
    mt = records("sfmta-board", "since-2019-01-01", 0, "meetings")
    hits = records("sfmta-board", "since-2019-01-01", 0, "matches")
    key = ("date", "no", "agenda", "title")
    return [
        Table("sfmta-board/meetings", mt, floor=380, max_drop=0.05, key=("date", "clipId"),
              required=["date", "clipId"], dates={"date": ("2000-01-01", "+120")}),
        Table("sfmta-board/agendas", ag, floor=170, max_drop=0.05, key="agenda",
              required=["date", "agenda", "itemCount"], dates={"date": ("2019-01-01", "+120")}),
        Table("sfmta-board/matches", hits, floor=120, max_drop=0.05, key=key, required=["date", "no", "title"]),
        extract_read("sfmta-board", "since-2019-01-01"),
        Join("sfmta-board matches~agendas",
             left=lambda r: None if ag(r) is None else [a["agenda"] for a in ag(r)],
             right=lambda r: None if hits(r) is None else sorted(set(h["agenda"] for h in hits(r))), drop_ok=True),
        Join("sfmta-board extract~report",
             left=lambda r: None if hits(r) is None else [tuple(h[k] for k in key) for h in hits(r)],
             right=lambda r: None if read_json(r, "out/sfmta-board/meetings.json") is None else [
                 tuple(h[k] for k in key) for h in read_json(r, "out/sfmta-board/meetings.json")["matches"]]),
    ]


def bos_checks(root):
    def searched(r):
        rows = []
        for p in sorted(glob.glob(os.path.join(r, ".cache", "bos-records", "*.json"))):
            try:
                with open(p, encoding="utf-8") as fh:
                    rows += json.load(fh)["rows"]
            except (ValueError, KeyError):
                continue
        return rows
    return [
        Table("bos-records/searched", searched, floor=2000, max_drop=0.05, required=["url", "file"]),
        Table("bos-records/matches", rows_of("out/bos-records/street-items.json", "matches"), floor=40,
              max_drop=0.10, key="item", required=[("date", 0.15), "item", "title", "url"],
              dates={"date": ("2019-01-01", "+120")}),
        # A record is dated by the meeting that acted on it, read from the
        # file's history; a meeting cannot come after the file's final action.
        Rule("bos-records/meeting-dates", rows_of("out/bos-records/street-items.json", "matches"),
             lambda rows: (lambda bad: (not bad, "%d of %d records lack a date basis or are dated after their final "
                                        "action%s" % (len(bad), len(rows), (": " + ", ".join(bad[:5])) if bad else "")))(
                 [r.get("item") or "?" for r in rows if not r.get("dateBasis")
                  or (r.get("date") and r.get("finalAction") and r["date"] > r["finalAction"])])),
    ]


def sfpuc_checks(root):
    meet = records("sfpuc-commission", "minutes", 0, "meetings")

    def items(r):
        m = meet(r)
        return None if m is None else [i for x in m for i in x["items"]]
    return [
        Table("sfpuc-commission/meetings", meet, floor=100, max_drop=0.05, key=("date", "url"),
              required=["date", "url", "items"], dates={"date": ("2019-01-01", "+1")}),
        Table("sfpuc-commission/items", items, floor=2500, max_drop=0.05, key=("date", "item", "url", "title"),
              required=["date", "item", ("title", 0.05)], dates={"date": ("2019-01-01", "+1")}),
        extract_read("sfpuc-commission", "minutes"),
        # The report keeps the decided items; each comes from a minutes file read.
        Join("sfpuc-commission items~report",
             left=lambda r: None if items(r) is None else [(i["date"], i["item"], i["url"], i["title"]) for i in items(r)],
             right=lambda r: None if read_json(r, "out/sfpuc-commission/items.json") is None else [
                 (i["date"], i["item"], i["url"], i["title"]) for i in read_json(r, "out/sfpuc-commission/items.json")["items"]],
             drop_ok=True),
    ]


def dpw_checks(root):
    ex = records("dpw-projects", "projects")
    out = rows_of("out/dpw-projects/projects.json", "projects")
    return [
        Table("dpw-projects/extract", ex, floor=240, max_drop=0.05, key="id",
              required=["id", "node", "url", "name", "status"]),
        extract_read("dpw-projects", "projects"),
        Join("dpw-projects extract~report",
             left=lambda r: None if ex(r) is None else [x["id"] for x in ex(r)],
             right=lambda r: None if out(r) is None else [x["id"] for x in out(r)]),
    ]


def mode_share_checks(root):
    acs = records("census-acs", "b08301-sf")
    commute = rows_of("site/data/mode-share.json", "commute")
    return [
        Table("census-acs/b08301-sf", acs, floor=8, max_drop=0.0, key="year",
              required=["year", "B08301_001E", "B08301_018E"], dates={year("year"): ("2010-01-01", "+1")}),
        extract_read("census-acs", "b08301-sf"),
        Join("census-acs extract~mode-share",
             left=lambda r: None if acs(r) is None else [x["year"] for x in acs(r)],
             right=lambda r: None if commute(r) is None else [x["year"] for x in commute(r)]),
    ]


def osm_checks(root):
    rel = "data/osm-cache/sf-bikeways-clipped.json"

    def no_overpass_error(b):
        # Overpass answers a timeout with HTTP 200, a "remark" and part of the data.
        return None if b.get("remark") else "ok"

    def compared(r):
        d = read_json(r, "out/osm-compare/compare.geojson")
        return None if d is None else [f["properties"] for f in d["features"] if f["properties"]["verdict"] != "osm-only"]

    def summary_blocks(r):
        d = read_json(r, "out/osm-compare/summary.json")
        return None if d is None else list(range(d["blocks"]))
    return [
        Table("osm/response", lambda r: None if read_json(r, rel) is None else [read_json(r, rel)], floor=1,
              max_drop=None, required=[no_overpass_error]),
        Table("osm/ways", rows_of(rel, "elements"), floor=5000, max_drop=0.10, key="id",
              required=["id", "tags", "geometry"], dates={"timestamp": ("2004-01-01", "+1")}),
        Table("osm-compare/blocks", compared, floor=2500, max_drop=0.05, key="cnn", required=["cnn", "verdict"]),
        # Each SFMTA block the summary counts is one feature of the map.
        Join("osm-compare summary~features",
             left=summary_blocks, right=lambda r: None if compared(r) is None else list(range(len(compared(r))))),
    ]


def street_work_checks(root):
    import csv

    def mpf(r):
        d = read_json(r, ".cache/street-work/mpf_network.json")
        return None if d is None else [x for x in d if x.get("CNN")]

    def rows(r):
        p = os.path.join(r, "out", "street-work", "street-work.csv")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    return [
        Table("street-work/priority-layer", mpf, floor=15000, max_drop=0.05, key="CNN", required=["CNN"]),
        Table("street-work/list", rows, floor=200, max_drop=0.25, key="DotMaps id",
              required=["DotMaps id", "Project", "Agency", ("Start", 0.10)],
              dates={"Start": ("2000-01-01", "2080-01-01"), "End": ("2000-01-01", "2080-01-01")}),
    ]


def _script_module(name):
    return paths.load(name + ".py")


def _linked(m):
    return m.get("confidence") in ("high", "medium") and m.get("pageKind") in ("project", "contract")


class Rule(object):
    """A check lib/quality.py's Table cannot say: `test(rows)` returns (ok, detail) for the rows `load` gives."""

    def __init__(self, name, load, test):
        self.name, self.load, self.test = name, load, test

    def check(self, rows, prev, today):
        if rows is None:
            return [Result(self.name + ".present", False, "no data on disk")]
        ok, detail = self.test(rows)
        return [Result(self.name, ok, detail)]


def model_filter(root, rel):
    """For a page-dates file: the previous data's pages cut to those the current file's model answered, so the
    row-count checks compare like with like. When the reader changes (TypeSafe's Jev to Claude, 2026-09-30) the
    previous data has none of the new model's picks, and the count bound is skipped for that run instead of
    comparing one model's picks with another's; after it, a fall is caught as before."""
    def cut(r, ps):
        if ps is None or r == root:
            return ps
        cur = (read_json(root, rel) or {}).get("model")
        return [p for p in ps if p.get("model") == cur]
    return cut


def page_dates_checks(root):
    """tools/projects/sfmta-page-dates.py: the construction and consultation dates a model read, one entry per sitemap page."""
    rel = "out/sfmta-page-dates/dates.json"
    pages = rows_of(rel, "pages")
    site = records("sfmta-pages", "sitemap")
    same_model = model_filter(root, rel)

    def answered(r):
        ps = pages(r)
        return None if ps is None else [p for p in ps if p.get("status") == "answered"]

    def picks(r):
        ps = same_model(r, answered(r))
        return None if ps is None else [dict(v, node=p["node"], field=f) for p in ps
                                         for f, v in sorted(p["fields"].items()) if v.get("iso")]

    def value(v):
        # The date at the page's precision (YYYY, YYYY-MM or YYYY-MM-DD). A
        # start is the first day of that period. An end or a consultation is
        # its last day, which is no earlier than the value and at most in the
        # next year (a season range, or a winter that runs into January).
        x = v.get("value") or ""
        if not re.fullmatch(r"20\d\d(-(0[1-9]|1[0-2])(-[0-3]\d)?)?", x):
            return None
        if v["field"] != "construction_start":
            return x if x <= v["iso"][:len(x)] and int(v["iso"][:4]) <= int(x[:4]) + 1 else None
        return x if v["iso"].startswith(x) else None

    def picked(r):
        # Every answer that names a span, read or not.
        ps = answered(r)
        return None if ps is None else [dict(v, node=p["node"], field=f) for p in ps
                                         for f, v in sorted(p["fields"].items()) if v.get("span")]

    def pick_share(label, pred, most):
        def test(rows):
            n = sum(1 for v in rows if pred(v))
            return n <= most * max(len(rows), 1), "%d of %d picks %s, at most %d%% allowed" % (
                n, len(rows), label, round(100 * most))
        return test

    def within_page(rows):
        # latestDate is worked out from every date-like span on the project
        # page, apart from Jev's answers, so a kept date past it means one of
        # the two readings of the page is wrong. A date from a linked notice
        # page is not held to it (it is flagged for a person instead), nor is
        # one a person checked.
        bad = ["%s %s" % (p["title"], f) for p in rows for f, v in sorted(p["fields"].items())
               if v.get("iso") and not v.get("linked") and not v.get("confirmed")
               and (p.get("latestDate") or "") < v["iso"]]
        return not bad, "%d kept dates fall after the latest date on their page%s" % (
            len(bad), (": " + ", ".join(bad[:4])) if bad else "")

    def end_before_start(rows):
        bad = [p["title"] for p in rows if (p["fields"]["construction_end"].get("iso") or "9") <
               (p["fields"]["construction_start"].get("iso") or "0")]
        return not bad, "%d of %d answered pages end before they start%s" % (
            len(bad), len(rows), (": " + ", ".join(bad[:4])) if bad else "")

    def share(label, pred, most):
        def test(rows):
            n = sum(1 for p in rows if pred(p))
            return n <= most * max(len(rows), 1), "%d of %d %s, at most %d%% allowed" % (
                n, len(rows), label, round(100 * most))
        return test

    def confirmed(r):
        # The hand-checked answers, with the pages they name.
        import csv
        ps = answered(r)
        path = os.path.join(r, "data", "sfmta-page-dates", "confirmed.csv")
        if ps is None or not os.path.exists(path):
            return None
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return {"rows": rows, "pages": {p["node"]: p for p in ps}}

    def confirmations(d):
        # Each row names an answered page and a published field once, gives a
        # date or `none`, who checked it and when; and the page carries it.
        bad, seen = [], set()
        for i, c in enumerate(d["rows"], 2):
            k = ((c.get("node") or "").strip(), (c.get("field") or "").strip())
            a, who, when = ((c.get(x) or "").strip() for x in ("answer", "who", "date"))
            p = d["pages"].get(k[0])
            if (k in seen or p is None or k[1] not in p["fields"] or not who
                    or not re.fullmatch(r"20\d\d-\d\d-\d\d", when)
                    or not (a == "none" or re.search(r"\b20\d\d\b", a))
                    or (p["fields"][k[1]].get("confirmed") or {}).get("answer") != a):
                bad.append("line %d" % i)
            seen.add(k)
        return not bad, "%d hand-checked answers, %d malformed or not applied%s" % (
            len(d["rows"]), len(bad), (": " + ", ".join(bad[:4])) if bad else "")

    def review_lists_flags(r):
        ps = answered(r)
        path = os.path.join(r, "out", "sfmta-page-dates", "review.md")
        if ps is None or not os.path.exists(path):
            return None
        text = open(path, encoding="utf-8").read()
        return [{"flagged": sum(1 for p in ps for v in p["fields"].values() if v.get("flags")),
                 "listed": text.count("\n- flagged: ")}]

    return [
        Table("sfmta-page-dates/pages", pages, floor=350, max_drop=0.05, key="node",
              required=["node", "url", "status"]),
        Table("sfmta-page-dates/answered", answered, floor=330, max_drop=0.05, key="node",
              required=["hash", "model", "asked", "fields"], dates={"asked": ("2026-09-01", "+1")}),
        # The page's own Project Status field, read beside the request: a list,
        # empty where the page has none (192 of 417 pages have one, 2026-09-29).
        Rule("sfmta-page-dates/project-status", answered,
             lambda rows: (all(isinstance(p.get("projectStatus"), list) for p in rows),
                           "%d of %d answered pages carry a Project Status" % (
                               sum(1 for p in rows if p.get("projectStatus")), len(rows)))),
        Rule("sfmta-page-dates/within-page", answered, within_page),
        # The floor on pages with any date: 313 of 397 answered pages on 2026-09-29.
        Table("sfmta-page-dates/with-a-date",
              lambda r: None if answered(r) is None else [p for p in same_model(r, answered(r))
                                                          if any(v.get("iso") for v in p["fields"].values())],
              floor=250, max_drop=0.10),
        # Each date parses, sits in range, and agrees with the value it was read as.
        Table("sfmta-page-dates/dates", picks, floor=500, max_drop=0.10, required=["span", "iso", value],
              dates={"iso": ("2000-01-01", "2045-12-31")}),
        Rule("sfmta-page-dates/end-not-before-start", answered, end_before_start),
        # Dropping an end that falls before the start is meant for a page with
        # phases; many would mean Jev is misreading which date is which.
        Rule("sfmta-page-dates/ends-dropped", answered,
             share("pages had a start or an end dropped as out of order", lambda p: p.get("conflicts"), 0.03)),
        # A span Jev picked that has no year on it or its line is left unread
        # (19 of 655 picks, 2026-09-29); many would mean candidates lost their
        # years, or read_span broke.
        Rule("sfmta-page-dates/unread", picked,
             pick_share("left unread", lambda v: v.get("unread"), 0.06)),
        # A kept date Jev all but guessed: under 0.10 confidence.
        Rule("sfmta-page-dates/low-confidence", picks,
             pick_share("kept at under 0.10 confidence", lambda v: v["confidence"] < 0.10, 0.03)),
        # The flag rule flagged 15 of 116 gold picks and about 14% of shown
        # dates on 2026-09-29. Flagged or checked by hand, far more than 40%
        # would bury the review file, and none would mean the rule stopped
        # firing; a checked date is no longer flagged, so both count.
        Rule("sfmta-page-dates/flagged", picks,
             lambda rows: (0 < sum(1 for v in rows if v.get("flags") or v.get("confirmed")) <= 0.40 * len(rows),
                           "%d of %d shown dates flagged for a person and %d checked by hand, at most 40%% allowed" % (
                               sum(1 for v in rows if v.get("flags")), len(rows),
                               sum(1 for v in rows if v.get("confirmed"))))),
        # review.md is rewritten with dates.json; a mismatch means one write
        # failed or the file was edited by hand.
        Rule("sfmta-page-dates/review-file", review_lists_flags,
             lambda rows: (rows[0]["flagged"] == rows[0]["listed"],
                           "review.md lists %d of %d flagged dates" % (rows[0]["listed"], rows[0]["flagged"]))),
        Rule("sfmta-page-dates/confirmations", confirmed, confirmations),
        Rule("sfmta-page-dates/not-asked", pages,
             share("pages never answered", lambda p: p.get("status") in ("not asked", "no page copy"), 0.05)),
        # Every sitemap page has exactly one entry, and nothing else does.
        Join("sfmta-page-dates sitemap~dates",
             left=lambda r: None if site(r) is None else [str(x["node"]) for x in site(r)],
             right=lambda r: None if pages(r) is None else [p["node"] for p in pages(r)]),
    ]


def dept_page_dates_checks(root):
    """tools/projects/sfmta-page-dates.py --pages departments: the model's dates off Public Works' and SFPUC's project pages,
    one entry per project page in out/department-pages/pages.json."""
    rel = "out/dept-page-dates/dates.json"
    pages = rows_of(rel, "pages")
    source = rows_of("out/department-pages/pages.json", "pages")
    same_model = model_filter(root, rel)

    def answered(r):
        ps = pages(r)
        return None if ps is None else [p for p in ps if p.get("status") == "answered"]

    def picks(r):
        ps = same_model(r, answered(r))
        return None if ps is None else [dict(v, node=p["node"], field=f) for p in ps
                                         for f, v in sorted(p["fields"].items()) if v.get("iso")]

    def fields_present(rows):
        bad = [p["node"] for p in rows if set(p.get("fields") or {}) != {"construction_start", "construction_end",
                                                                          "consultation"}]
        return not bad, "%d of %d answered pages lack one of the three fields%s" % (
            len(bad), len(rows), (": " + ", ".join(bad[:3])) if bad else "")

    def end_before_start(rows):
        bad = [p["title"] for p in rows if (p["fields"]["construction_end"].get("iso") or "9") <
               (p["fields"]["construction_start"].get("iso") or "0")]
        return not bad, "%d of %d answered pages end before they start%s" % (
            len(bad), len(rows), (": " + ", ".join(bad[:4])) if bad else "")

    def review_lists_flags(r):
        ps = answered(r)
        path = os.path.join(r, "out", "dept-page-dates", "review.md")
        if ps is None or not os.path.exists(path):
            return None
        text = open(path, encoding="utf-8").read()
        return [{"flagged": sum(1 for p in ps for v in p["fields"].values() if v.get("flags")),
                 "listed": text.count("\n- flagged: ")}]

    def never_answered(rows):
        n = sum(1 for p in rows if p.get("status") in ("not asked", "no page copy"))
        return n <= 0.05 * max(len(rows), 1), "%d of %d pages never answered, at most 5%% allowed" % (n, len(rows))

    # Counts on 2026-09-29: 410 project pages (344 Public Works, 66 SFPUC).
    return [
        Table("dept-page-dates/pages", pages, floor=350, max_drop=0.05, key="node",
              required=["node", "url", "status", "department"]),
        Table("dept-page-dates/answered", answered, floor=250, max_drop=0.05, key="url",
              required=["hash", "model", "asked", "fields"], dates={"asked": ("2026-09-01", "+1")}),
        Rule("dept-page-dates/fields", answered, fields_present),
        # Every date shown parses and lies between 2000 and 2040.
        Table("dept-page-dates/dates", picks, floor=150, max_drop=0.10, required=["span", "iso", "value"],
              dates={"iso": ("2000-01-01", "2040-12-31"), "first": ("2000-01-01", "2040-12-31"),
                     "last": ("2000-01-01", "2040-12-31")}),
        Rule("dept-page-dates/end-not-before-start", answered, end_before_start),
        Rule("dept-page-dates/review-file", review_lists_flags,
             lambda rows: (rows[0]["flagged"] == rows[0]["listed"],
                           "review.md lists %d of %d flagged dates" % (rows[0]["listed"], rows[0]["flagged"]))),
        Rule("dept-page-dates/not-asked", pages, never_answered),
        # Every Public Works and SFPUC project page has exactly one entry, and nothing else does.
        Join("dept-page-dates pages~dates",
             left=lambda r: None if source(r) is None else [
                 p["url"] for p in source(r) if p.get("department") in ("Public Works", "SFPUC")
                 and p.get("kind") == "project"],
             right=lambda r: None if pages(r) is None else [p["node"] for p in pages(r)]),
    ]


def dept_pages_checks(root):
    pages = rows_of("out/department-pages/pages.json", "pages")
    matches = rows_of("out/department-pages/matches.json", "matches")
    record = rows_of("out/project-record/projects.json", "projects")
    puc = rows_of("data/extract/sfpuc-projects/projects.json", "records")
    dpp = _script_module("department-project-pages")

    def linked(r):
        m = matches(r)
        return None if m is None else [x for x in m if _linked(x)]

    def closest(r):
        m = matches(r)
        return None if m is None else [x["closest"] | {"id": x["id"]} for x in m if x.get("closest")]
    return [
        Table("department-pages/pages", pages, floor=700, max_drop=0.05, key=("department", "url"),
              required=["department", "url", "title"]),
        # One row per feed job, whatever it matched.
        Table("department-pages/matches", matches, floor=250, max_drop=0.10, key="id",
              required=["id", "department", "name"]),
        # A job linked to its own page carries the page's address, title and department.
        Table("department-pages/linked", linked, floor=120, max_drop=0.15, key="id",
              required=["url", "title", "pageDepartment", "method"]),
        # A closest official source says what it is and why it is the closest.
        Table("department-pages/closest", closest, floor=40, max_drop=0.20, key="id",
              required=["url", "title", "department", "why"]),
        # A match points at a page that was read (or at none, when no page matched).
        Join("department-pages matches~pages",
             left=lambda r: None if pages(r) is None else [p["url"] for p in pages(r)],
             right=lambda r: None if matches(r) is None else sorted(set(m["url"] for m in matches(r) if m.get("url"))),
             drop_ok=True),
        # Every match is a feed job the project record carries, once: the join
        # from the record's jobs to their matches invents and repeats none. The
        # record's jobs from other agencies have no match row, by design.
        Join("department-pages record~matches",
             left=lambda r: None if record(r) is None else [p["id"] for p in record(r) if p["id"].startswith("dotmaps:")],
             right=lambda r: None if matches(r) is None else [m["id"] for m in matches(r)], drop_ok=True),
        # SFPUC's own project list: one record per project page, each with a
        # name, its sfpuc.gov address and a status, and every record a page
        # that was read.
        Table("sfpuc-projects", puc, floor=45, max_drop=0.15, key="id", required=["id", "name", "url", "status"]),
        Join("sfpuc-projects~pages",
             left=lambda r: None if pages(r) is None else [p["url"] for p in pages(r) if p["department"] == "SFPUC"],
             right=lambda r: None if puc(r) is None else [p["url"] for p in puc(r)], drop_ok=True),
        # Each page read by hand (READ_PAGES) is still in the harvest and still
        # gives its job its page; a page that drops out leaves the job unlinked.
        # A job the project record no longer lists (it finished: 8181, Folsom
        # Streetscape, ended 2026-10-16) has nothing to link. A job the record
        # still lists must still link, whether or not it has a match row.
        Join("department-pages read-pages~linked",
             left=lambda r: None if record(r) is None else sorted(
                 {p["id"] for p in record(r)} & {"dotmaps:" + k for k in dpp.READ_PAGES}),
             right=lambda r: None if linked(r) is None else [m["id"] for m in linked(r)
                                                             if m["id"][len("dotmaps:"):] in dpp.READ_PAGES],
             extra_ok=False),
    ]


def month_start(field):
    """A date field published as a year or a month ("2019", "2016-02") read as its first day."""
    def f(r):
        v = str(r.get(field) or "")
        return v + "-01-01" if re.match(r"^\d{4}$", v) else v + "-01" if re.match(r"^\d{4}-\d{2}$", v) else v or None
    f.__name__ = field
    return f


# A Public Works page row is placed from its page's Location field
# (lib/pw_extent.py). The largest such row holds 59 blocks (Geneva
# Avenue Traffic Signal Project, 2026-09-29); a row of 90 or more is a Location
# read as whole streets (Alemany Interchange held 91 before the interchange
# rule, Innes Avenue 17 for two blocks).
PAGE_EXTENT_MAX_BLOCKS = 90


RATING_STATES = {"percent": True, "scope-none": True, "already-built": False, "not-stated": False, "no-overlap": False}
RATING_BANDS = {"all", "most", "some", "none", "already-built", "not-stated", "no-overlap"}


def plan_rating_fault(p):
    """None when the row's planRating is sound, else what is wrong with it."""
    r = p.get("planRating")
    if not isinstance(r, dict):
        return "%s: no planRating" % p.get("name")
    st, v = r.get("state"), r.get("value")
    if st not in RATING_STATES:
        return "%s: planRating state %r is not a named state" % (p.get("name"), st)
    if RATING_STATES[st]:
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
            return "%s: planRating value %r is not a whole percent from 0 to 100" % (p.get("name"), v)
        if st == "scope-none" and v != 0:
            return "%s: 0%% in published scope carries %r" % (p.get("name"), v)
    elif v is not None:
        return "%s: state %s carries a value %r" % (p.get("name"), st, v)
    if not r.get("label"):
        return "%s: planRating has no label" % p.get("name")
    if r.get("band") not in RATING_BANDS:
        return "%s: planRating band %r" % (p.get("name"), r.get("band"))
    srcs = r.get("sources") or []
    if not srcs or any(not s.get("label") or not str(s.get("url") or "").startswith("http") for s in srcs):
        return "%s: planRating has no linked source" % p.get("name")
    if st == "percent" and (r.get("baseMiles") or 0) <= 0:
        return "%s: a percent with no base miles" % p.get("name")
    if (r.get("builtMiles") or 0) > (r.get("baseMiles") or 0):
        return "%s: builds %s mi of a %s mi base" % (p.get("name"), r.get("builtMiles"), r.get("baseMiles"))
    # The miles are rounded to two figures, so the percent they give is
    # within a few points of the value, not exact.
    if st == "percent" and abs(100.0 * r["builtMiles"] / r["baseMiles"] - v) > 6:
        return "%s: %s%% disagrees with %s of %s mi" % (p.get("name"), v, r["builtMiles"], r["baseMiles"])
    return None


def coordination_checks(root):
    rows = rows_of("site/data/coordination.json", "projects")
    matches = rows_of("out/department-pages/matches.json", "matches")

    def registry(r):
        d = read_json(r, "data/project-ids.json")
        return None if d is None else [{"slug": k} | v for k, v in sorted(d.items())]

    def all_ids(r):
        x = rows(r)
        return None if x is None else [{"id": i} for p in x for i in [p["id"]] + list(p.get("alsoIds") or [])]

    def page_extent(p):
        if p.get("source") in ("dpw-page", "puc-page") and (p.get("blocks") or 0) >= PAGE_EXTENT_MAX_BLOCKS:
            return "%s holds %d blocks" % (p["name"], p["blocks"])
        return None

    def link_urls(p):
        return {l.get("url") for l in p.get("links") or []}

    def ids_of(p):
        return [p["id"]] + list(p.get("alsoIds") or [])

    def matched(r, carried):
        """Feed jobs a listed row holds whose department page was matched; with `carried`, only where the row
        links that page, or is an SFMTA row, which links its own page in the job's place."""
        x, m = rows(r), matches(r)
        if x is None or m is None:
            return None
        want = {mm["id"]: mm["url"] for mm in m if _linked(mm)}
        return [pid for p in x for pid in sorted(set(ids_of(p))) if pid in want
                and (not carried or want[pid] in link_urls(p) or p["source"] == "sfmta")]
    return [
        Table("coordination/projects", rows, floor=200, max_drop=0.10, max_growth=0.25, key="slug",
              required=["id", "slug", "name", "department", "source", "kind", "links",
                        ("phase", 0.20), ("start", 0.30)],
              dates={month_start("start"): ("2000-01-01", "2045-12-31"),
                     month_start("end"): ("2000-01-01", "2045-12-31")}),
        # One row per project: no id, feed job or merged id on two rows.
        Table("coordination/ids", all_ids, floor=200, max_drop=0.10, key="id", required=["id"]),
        Each("coordination/page-extent", rows, page_extent,
             "no Public Works page row holds %d or more blocks" % PAGE_EXTENT_MAX_BLOCKS),
        # A row's meetings (tools/meetings/upcoming-meetings.py through project-record.py):
        # each dated, named and linked, in date order.
        Each("coordination/meetings", rows,
             lambda p: next(("%s: meeting %r lacks %s" % (p["name"], m.get("date"), f)
                             for m in p.get("meetings") or () for f in ("date", "body", "url", "title") if not m.get(f)),
                            None) or ("%s: meetings out of date order" % p["name"]
                                      if [m["date"] for m in p.get("meetings") or ()] != sorted(m["date"] for m in p.get("meetings") or ()) else None),
             "every meeting on a row is dated, named and linked, in date order"),
        # The plan rating (tools/projects/coordination-projects.py plan_rating): a
        # whole percent from 0 to 100 or one of the named states, and a
        # linked source for every value.
        Each("coordination/plan-rating", rows, plan_rating_fault,
             "every row's plan rating is 0 to 100 or a named state, and names a linked source"),
        # Bryan, 2026-11-09: no finished project shows. A listed row whose end is before the date its data was
        # read (the file's `today`), or before the day the check runs, fails the build.
        Each("coordination/no-finished", lambda r: None if read_json(r, "site/data/coordination.json") is None else [
                 dict(p, _day=max(read_json(r, "site/data/coordination.json")["today"], date_today()))
                 for p in rows(r)],
             lambda p: ("%s ended %s, before %s" % (p["name"], p["end"], p["_day"])
                        if p.get("end") and str(p["end"])[:10] < p["_day"] else None),
             "no listed project ended before its data was read or before today"),
        Each("coordination/dates", rows,
             lambda p: ("%s ends %s before it starts %s" % (p["name"], p["end"], p["start"])
                        if p.get("start") and p.get("end") and str(p["end"])[:7] < str(p["start"])[:7] else None),
             "no row ends before it starts"),
        # Every listed row has its address in the registry, listed, and the
        # registry lists no address the list lacks.
        Join("coordination registry~projects",
             left=lambda r: None if registry(r) is None else [x["slug"] for x in registry(r) if x.get("listed")],
             right=lambda r: None if rows(r) is None else [p["slug"] for p in rows(r)]),
        # A listed feed job that its department's page matches carries that
        # page's link: the join from matches to rows drops and repeats none.
        Join("coordination matches~links", left=lambda r: matched(r, False), right=lambda r: matched(r, True)),
    ]


def date_today():
    """The day the check runs. SF_REFRESH_TODAY overrides it, so a test can watch a check fail on a later day."""
    import datetime as _dt
    return os.environ.get("SF_REFRESH_TODAY") or _dt.date.today().isoformat()


def finished_listed(root=ROOT, day=None):
    """Listed projects in site/data/coordination.json whose published end is before `day` (default today)."""
    d = read_json(root, "site/data/coordination.json") or {}
    day = day or date_today()
    return [p["name"] for p in d.get("projects", []) if p.get("end") and str(p["end"])[:10] < day]


UPCOMING_REL = "data/upcoming-meetings/meetings.json"


def upcoming_checks(root):
    """Meetings not yet held (tools/meetings/upcoming-meetings.py)."""
    meetings = rows_of(UPCOMING_REL, "meetings")
    sources = rows_of(UPCOMING_REL, "sources")

    def items(r):
        ms = meetings(r)
        return None if ms is None else [dict(it, _mid=m["id"]) for m in ms for it in m.get("items") or ()]

    def agenda_rule(m):
        if m.get("agendaPosted") != bool(m.get("items")):
            return "%s: agendaPosted %s with %d items" % (m["id"], m.get("agendaPosted"), len(m.get("items") or ()))
        return None

    def floor_rule(src):
        # SFMTA's Board alone meets twice a month, so a read of its listing
        # that finds fewer than three meetings in 90 days is a broken parse.
        want = {"sfmta": 3}.get(src["id"], 0)
        if src.get("status") == "read" and src.get("meetings", 0) < want:
            return "%s read %d meetings, fewer than %d" % (src["id"], src["meetings"], want)
        return None

    def personal(m):
        # The scrub's own rule (lib/extract.py): institutional inboxes stay.
        from extract import EMAIL, KEEP
        bad = [e for e in EMAIL.findall(json.dumps(m, ensure_ascii=False)) if not KEEP.match(e)]
        return "%s carries a personal address" % m["id"] if bad else None

    return [
        Table("upcoming/meetings", meetings, floor=5, max_drop=None, key="id",
              required=["id", "source", "kind", "body", "date", "title", "url"],
              dates={"date": ("-1", "+100")}),
        Table("upcoming/sources", sources, floor=4, max_drop=None, key="id", required=["id", "status", "listing"]),
        # Each agenda point once per meeting.
        Table("upcoming/items", items, floor=0, max_drop=None,
              key=lambda it: (it["_mid"], str(it.get("no")), it.get("title")), required=["title", "url"]),
        Each("upcoming/agenda-posted", meetings, agenda_rule, "a meeting is marked agenda-posted exactly when it has items"),
        Each("upcoming/source-floor", sources, floor_rule, "each source read finds at least its floor of meetings"),
        Each("upcoming/no-personal-email", meetings, personal, "no individual staff email address in a meeting"),
    ]


def overlap_checks(root):
    doc = lambda r: read_json(r, "site/data/department-overlap.json")  # noqa: E731
    projects = rows_of("site/data/department-overlap.json", "projects")
    coord = rows_of("site/data/coordination.json", "projects")

    def jobs(r):
        d = doc(r)
        return None if d is None else [{"slug": k} | v for k, v in sorted(d["jobs"].items())]

    def plan_of(r):
        c = coord(r)
        return None if c is None else {p["slug"]: set(p.get("planCnns") or []) for p in c}

    def off_plan(r):
        plan, j = plan_of(r), jobs(r)
        if plan is None or j is None:
            return None
        return [{"slug": x["slug"], "bad": sorted(set(x.get("cnns") or []) - plan.get(x["slug"], set()))} for x in j]
    return [
        Table("department-overlap/projects", projects, floor=150, max_drop=0.15, max_growth=0.30, key="slug",
              required=["slug", "name", "department", "kind", ("miles", 0.0)]),
        Table("department-overlap/jobs", jobs, floor=60, max_drop=0.20, max_growth=0.30, key="slug",
              required=["slug", "cnns", ("overlapMiles", 0.0)]),
        # Every project and job is a listed project on the Current Projects list.
        Join("department-overlap projects~coordination",
             left=lambda r: None if coord(r) is None else [p["slug"] for p in coord(r)],
             right=lambda r: None if projects(r) is None else [p["slug"] for p in projects(r)], drop_ok=True),
        Join("department-overlap jobs~coordination",
             left=lambda r: None if coord(r) is None else [p["slug"] for p in coord(r)],
             right=lambda r: None if jobs(r) is None else [p["slug"] for p in jobs(r)], drop_ok=True),
        # A job's overlap blocks are plan blocks its listed project covers.
        Each("department-overlap/job-blocks", off_plan,
             lambda x: ("%s: %d blocks not among its plan blocks (%s)" % (x["slug"], len(x["bad"]), ", ".join(x["bad"][:3]))
                        if x["bad"] else None), "every job's blocks are its project's plan blocks"),
        Each("department-overlap/miles", jobs,
             lambda x: ("%s: overlap %.2f mi" % (x["slug"], x["overlapMiles"])
                        if not isinstance(x.get("overlapMiles"), (int, float)) or x["overlapMiles"] < 0 else None),
             "no negative or missing overlap"),
    ]


def removals_checks(root):
    doc = lambda r: read_json(r, "site/data/bike-history/removed.json")  # noqa: E731
    corridors = rows_of("site/data/bike-history/removed.json", "slow_streets")
    bikeways = rows_of("site/data/bike-history/removed.json", "bikeways")

    def blocks(r):
        c = corridors(r)
        return None if c is None else [dict(b, corridor=x["id"]) for x in c for b in x["blocks"]]

    def summary(r):
        d = doc(r)
        return None if d is None else [d["summary"]]
    return [
        Table("bike-removals/corridors", corridors, floor=30, max_drop=0.10, key="id", required=["id", "words", "street", "installed", "fate"]),
        # One corridor per block: a block in two corridors would count twice.
        Table("bike-removals/corridor-blocks", blocks, floor=250, max_drop=0.10, key="cnn", required=["cnn", "status", "pts"]),
        Table("bike-removals/bikeways", bikeways, floor=0, max_drop=None, key="key", required=["key", "seen", "gone_by", "miles"],
              dates={"seen": ("2021-01-01", "+1"), "gone_by": ("2021-01-01", "+1")}),
        Each("bike-removals/unresolved", corridors,
             lambda c: "%s did not resolve: %s" % (c["id"], c["unresolved"]) if c.get("unresolved") and c["id"] != "lombard" else None,
             "every corridor with an extent resolves to centerline blocks"),
        Each("bike-removals/window", bikeways,
             lambda b: "%s seen %s, gone %s" % (b["key"], b["seen"], b["gone_by"]) if not b["seen"] < b["gone_by"] else None,
             "every bikeway removal is dated by an earlier copy and a later one"),
        Each("bike-removals/kept-covered", corridors,
             lambda c: "%s is kept by the 2022 report but none of it is in hkz3-itiu" % c["id"]
             if c["fate"] == "kept" and c["blocks"] and c["kept_street_miles"] + c["readopted_street_miles"] <= 0 else None,
             "every corridor the 2022 report kept is at least partly in hkz3-itiu"),
        Each("bike-removals/removed-not-kept", corridors,
             lambda c: "%s is dropped by the 2022 report but mostly in hkz3-itiu from before 2023" % c["id"]
             if c["fate"] == "removed" and c["blocks"] and c["kept_street_miles"] > 0.2 * sum(b["street_miles"] for b in c["blocks"]) else None,
             "no corridor the 2022 report dropped is mostly still in hkz3-itiu"),
        Each("bike-removals/block-count", summary,
             lambda s: "%d bikeway blocks removed; a capture probably lost rows" % s["bikeway_blocks_removed"]
             if s["bikeway_blocks_removed"] > 60 else None, "no more than 60 bikeway blocks removed"),
        # The dropped figure the page prints (removed.json) is the drop the
        # all-ages series shows (history.json) in the same year.
        Each("bike-removals/dropped-matches-history", _dropped_pair,
             lambda p: "removed.json slow_street_dropped_miles %s, history.json drop in %s %s" % p
             if p[2] is None or abs(p[0] - p[2]) > 0.05 else None,
             "removed.json's dropped miles equal the history's drop within 0.05"),
        Each("bike-removals/miles", summary,
             lambda s: "pandemic Slow Street miles removed %.1f outside 5-60" % s["slow_street_removed_miles"]
             if not 5 <= s["slow_street_removed_miles"] <= 60 else None,
             "pandemic Slow Street miles removed are within 5-60"),
    ]


def _dropped_pair(r):
    d, h = read_json(r, "site/data/bike-history/removed.json"), read_json(r, "site/data/bike-history/history.json")
    if d is None or h is None:
        return None
    row = next((x for x in h["rows"] if x["year"] == d.get("dropped_year")), None)
    drop = row.get("pandemic_dropped_miles") if row else None
    return [(d["summary"].get("slow_street_dropped_miles", -1), d.get("dropped_year"), drop)]


def walk_checks(root):
    """tools/travel/osm-walk-network.py: OpenStreetMap's walkable ways in the city, which walking distance is measured along."""
    rel = "data/osm-cache/sf-walk.json"

    def ways(r):
        d = read_json(r, rel)
        return None if d is None else [e for e in d["elements"] if e["type"] == "way"]

    def response(r):
        d = read_json(r, rel)
        return None if d is None else [d]

    def graph(r):
        if not os.path.exists(os.path.join(r, rel)):
            return None
        import walknet
        G = walknet.Graph(os.path.join(r, rel))
        return [{"nodes": len(G.x), "missing": G.missing_nodes, "largest": G.component_sizes[0] / max(len(G.x), 1),
                 "west": min(G.x), "east": max(G.x)}]
    return [
        Table("osm-walk/response", response, floor=1, max_drop=None,
              required=[lambda b: None if b.get("remark") else "ok"]),
        Table("osm-walk/ways", ways, floor=45000, max_drop=0.10, key="id", required=["id", "nodes", "tags"]),
        Each("osm-walk/two-nodes", ways, lambda w: "way %s has %d node" % (w["id"], len(w["nodes"])) if len(w["nodes"]) < 2 else None,
             "every way has at least two nodes"),
        # The same area name matches a dozen towns abroad; the box keeps them
        # out, and a way outside it means the box was lost.
        Each("osm-walk/in-city", graph, lambda g: "network spans %.0f km east-west" % ((g["east"] - g["west"]) / 1000)
             if g["east"] - g["west"] > 30000 else None, "the network lies within San Francisco's 30 km"),
        Each("osm-walk/nodes-resolved", graph, lambda g: "%d node ids have no coordinates" % g["missing"] if g["missing"] else None,
             "every way's nodes came back with coordinates"),
        Each("osm-walk/connected", graph, lambda g: "largest connected piece holds %.1f%% of nodes" % (100 * g["largest"])
             if g["largest"] < 0.90 else None, "at least 90% of the network is one connected piece"),
    ]


def drive_checks(root):
    """tools/travel/osm-drive-network.py: OpenStreetMap's drivable ways in the city, which school-sim routes a car along."""
    rel = "data/osm-cache/sf-drive.json"

    def ways(r):
        d = read_json(r, rel)
        return None if d is None else [e for e in d["elements"] if e["type"] == "way"]

    def response(r):
        d = read_json(r, rel)
        return None if d is None else [d]

    def graph(r):
        d = read_json(r, rel)
        if d is None:
            return None
        nodes = {e["id"]: (e["lon"], e["lat"]) for e in d["elements"] if e["type"] == "node"}
        ws = [e for e in d["elements"] if e["type"] == "way"]
        missing = sum(1 for w in ws for n in w["nodes"] if n not in nodes)
        parent = {}

        def find(a):
            while parent.get(a, a) != a:
                parent[a] = parent.get(parent[a], parent[a])
                a = parent[a]
            return a
        for w in ws:
            for a, b in zip(w["nodes"], w["nodes"][1:]):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
        used = set(n for w in ws for n in w["nodes"])
        sizes = {}
        for n in used:
            sizes[find(n)] = sizes.get(find(n), 0) + 1
        lons = [nodes[n][0] for n in used if n in nodes]
        names = set(w["tags"].get("name") for w in ws)
        return [{"missing": missing, "largest": max(sizes.values()) / max(len(used), 1), "spanDeg": max(lons) - min(lons),
                 "vanNess": "Van Ness Avenue" in names, "busway": sum(1 for w in ws if w["tags"].get("highway") == "busway")}]
    return [
        Table("osm-drive/response", response, floor=1, max_drop=None,
              required=[lambda b: None if b.get("remark") else "ok"]),
        Table("osm-drive/ways", ways, floor=15000, max_drop=0.10, key="id", required=["id", "nodes", "tags"]),
        Each("osm-drive/two-nodes", ways, lambda w: "way %s has %d node" % (w["id"], len(w["nodes"])) if len(w["nodes"]) < 2 else None,
             "every way has at least two nodes"),
        Each("osm-drive/in-city", graph, lambda g: "network spans %.2f degrees of longitude" % g["spanDeg"] if g["spanDeg"] > 0.3 else None,
             "the network lies within San Francisco"),
        Each("osm-drive/nodes-resolved", graph, lambda g: "%d node ids have no coordinates" % g["missing"] if g["missing"] else None,
             "every way's nodes came back with coordinates"),
        Each("osm-drive/connected", graph, lambda g: "largest connected piece holds %.1f%% of nodes" % (100 * g["largest"])
             if g["largest"] < 0.90 else None, "at least 90% of the drive network is one connected piece"),
        # The reason the fetch exists: a street whose sidewalks are their own ways is in it, and a busway is not.
        Each("osm-drive/streets", graph, lambda g: None if g["vanNess"] and not g["busway"] else
             "Van Ness Avenue %s; %d busways" % ("present" if g["vanNess"] else "missing", g["busway"]),
             "Van Ness Avenue is drivable and no busway is"),
    ]


def walk_reach_checks(root):
    """tools/bike-network/walk-reach.py: the explorer's walking levels per bikeway code."""
    rel = "site/data/bike-history/walk-reach.json"

    def strings(r):
        d = read_json(r, rel)
        if d is None:
            return None
        n = sum(d["counts"].values())
        return [{"net": net, "code": c, "s": v, "n": n, "top": len(d["thresholds"])} for net in ("today", "plan") for c, v in d[net].items()]

    def blocks(r):
        d = read_json(r, "site/data/bike-history/reach.json")
        return None if d is None else list(range(len(d["blocks"]["rows"])))

    def counted(r):
        d = read_json(r, rel)
        return None if d is None else list(range(d["counts"]["blocks"]))
    return [
        Table("walk-reach/strings", strings, floor=8, max_drop=0.0, key=lambda x: "%s:%s" % (x["net"], x["code"]), required=["s"]),
        Each("walk-reach/length", strings, lambda x: "%s %s has %d points for %d" % (x["net"], x["code"], len(x["s"]), x["n"])
             if len(x["s"]) != x["n"] else None, "one character per point"),
        Each("walk-reach/levels", strings, lambda x: "%s %s has a level outside 0-%d" % (x["net"], x["code"], x["top"])
             if set(x["s"]) - set("0123456789"[:x["top"] + 1]) else None, "every level is a threshold index or none"),
        # Every census block the history map shows has a walking level.
        Join("walk-reach blocks~reach.json", left=counted, right=blocks),
        # Private K-12 schools: enough of them, and none the same as a public one.
        Each("reach/private-schools", lambda r: None if read_json(r, "site/data/bike-history/reach.json") is None
             else [read_json(r, "site/data/bike-history/reach.json")["schools"]], _private_school_problem,
             "at least 80 private K-12 schools, none within 30 m of a public school"),
        # Built from the walk network now on disk, not an earlier copy.
        Each("walk-reach/current-network", lambda r: None if read_json(r, rel) is None else [read_json(r, rel)["network"]],
             lambda n: "built from the copy of %s; the cache is %s" % (n["fetched_on"], _walk_base(root))
             if _walk_base(root) and n["fetched_on"] != _walk_base(root) else None, "walk-reach.json matches the walk network cache"),
    ]


def _private_school_problem(schools):
    import math
    priv = [x for x in schools if x.get("private")]
    pub = [x for x in schools if not x.get("private")]
    if len(priv) < 80:
        return "%d private K-12 schools; expected at least 80" % len(priv)
    k = math.cos(math.radians(37.76)) * 111195.0
    near = [p["name"] for p in priv for q in pub
            if math.hypot((p["lon"] - q["lon"]) * k, (p["lat"] - q["lat"]) * 111195.0) <= 30 and not q.get("closed")]
    return "private schools within 30 m of an open public school: %s" % ", ".join(near[:4]) if near else None


def _walk_base(root):
    d = read_json(root, "data/osm-cache/sf-walk.json")
    return None if d is None else d.get("osm3s", {}).get("timestamp_osm_base")


def outline_checks(root):
    """pipeline/sources/census-block-outlines.py: one outline per census block, for both vintages."""
    out = []
    for v in ("2010", "2020"):
        outlines, points = records("census-blocks", "outlines-" + v), records("census-blocks", v)
        out += [Table("census-outlines/%s" % v, outlines, floor=5500, max_drop=0.0, key="geoid", required=["geoid", "rings"]),
                Each("census-outlines/%s-rings" % v, outlines, lambda o: "%s has an empty ring" % o["geoid"]
                     if any(len(r) < 4 for r in o["rings"]) else None, "every ring closes with at least four points"),
                Join("census-outlines %s~points" % v, left=lambda r, p=points: None if p(r) is None else [x["geoid"] for x in p(r)],
                     right=lambda r, o=outlines: None if o(r) is None else [x["geoid"] for x in o(r)]),
                extract_read("census-blocks", "outlines-" + v)]
    return out


def census_children_checks(root):
    """tools/school-trips/census-children.py: Census 2020 DHC P12 school-age children per block."""
    kids, points = records("census-dhc", "p12-blocks"), records("census-blocks", "2020")

    def pairs(r):
        k, p = kids(r), points(r)
        if k is None or p is None:
            return None
        pop = {x["geoid"]: x["pop"] for x in p}
        return [dict(x, pl=pop.get(x["geoid"])) for x in k]
    return [
        Table("census-dhc/p12-blocks", kids, floor=5900, max_drop=0.0, key="geoid",
              required=["geoid", "total", "a5_9", "a10_14", "a15_17"]),
        extract_read("census-dhc", "p12-blocks"),
        Join("census-dhc p12~2020 blocks", left=lambda r: None if points(r) is None else [x["geoid"] for x in points(r)],
             right=lambda r: None if kids(r) is None else [x["geoid"] for x in kids(r)]),
        # The Census Bureau holds block total population invariant between the
        # redistricting file and the DHC, so a mismatch is a broken read.
        Each("census-dhc/total-matches-pl", pairs, lambda x: "%s: DHC %s, PL %s" % (x["geoid"], x["total"], x["pl"])
             if x["total"] != x["pl"] else None, "each block's DHC total equals its PL 94-171 count"),
        Each("census-dhc/bands", kids, lambda x: "%s: bands exceed total" % x["geoid"]
             if min(x["a5_9"], x["a10_14"], x["a15_17"]) < 0 or x["a5_9"] + x["a10_14"] + x["a15_17"] > x["total"] else None,
             "age bands are non-negative and within the block total"),
    ]


def supervisor_districts_checks(root):
    """pipeline/sources/supervisor-districts.py: the 11 Supervisor District outlines the contact-officials block reads."""
    rows = json_rows("site/data/supervisor-districts.json", "districts")
    return [
        Table("supervisor-districts", rows, floor=11, max_drop=0.0, max_growth=0.0, key="district",
              required=["district", "coords"]),
        Each("supervisor-districts/numbers", rows, lambda x: None if x["district"] in range(1, 12)
             else "district %r is not 1 to 11" % x["district"], "each district is numbered 1 to 11"),
        Table("supervisor-districts.read-date", blob_meta("site/data/supervisor-districts.json", "read"),
              floor=1, max_drop=None, required=["read"], dates={"read": ("2025-01-01", "+1")}),
    ]


def sf_address_points_checks(root):
    """pipeline/sources/sf-address-points.py: the city's address points, one per side of each hundred block, for School Trips' address box."""
    rows = json_rows("site/data/sf-addresses.json", "streets")
    return [
        Table("sf-addresses", rows, floor=1500, max_drop=0.05, max_growth=0.20, key="s", required=["s", "p"]),
        Each("sf-addresses/points", rows, lambda x: None if x["p"] and all(-12320000 <= q[1] <= -12230000 and 3760000 <= q[2] <= 3790000 for q in x["p"])
             else "%s has no points or a point outside San Francisco" % x["s"], "every street has points, all inside San Francisco"),
        Table("sf-addresses.read-date", blob_meta("site/data/sf-addresses.json", "read"),
              floor=1, max_drop=None, required=["read"], dates={"read": ("2025-01-01", "+1")}),
    ]


def school_points_checks(root):
    """tools/school-trips/school-points.py: each school's CDE point against EAS's point for its street address.

    The simulation's own points are held to that file by school-sim.py's school-sim/school-points-near check, in
    the school-sim build step: a check here would fail on the previous run's index.json and stop the sim that fixes it."""

    def doc(r):
        return read_json(r, "data/school-sim/school-points.json")

    def rows(r):
        d = doc(r)
        return None if d is None else [dict(v, cds=k) for k, v in sorted(d["schools"].items())]

    return [
        Table("school-points", rows, floor=120, max_drop=0.05, key="cds", required=["cds", "name", "address"]),
        Each("school-points/matched", rows, lambda x: None if x.get("eas") else "%s %s: %s" % (x["cds"], x["name"], x.get("how")),
             "every active school's street address found in EAS"),
    ]


def ej_communities_checks(root):
    """pipeline/sources/ej-communities.py: SF Planning's Environmental Justice Communities map, and each census block's score on it."""
    polys, blocks = records("ej-communities", "polygons"), records("ej-communities", "blocks")
    points, kids = records("census-blocks", "2020"), records("census-dhc", "p12-blocks")

    def score_ok(x):
        s = x["score"]
        return None if isinstance(s, int) and (0 <= s <= 30 or s == 999) else "score %r out of range" % (s,)

    def shares(r):
        b, k = blocks(r), kids(r)
        if b is None or k is None:
            return None
        n = {x["geoid"]: x["a5_9"] + x["a10_14"] + x["a15_17"] for x in k}
        tot = sum(n.values())
        return [{"ej": sum(n.get(x["geoid"], 0) for x in b if x["ej"]) / float(tot or 1),
                 "unplaced": sum(n.get(x["geoid"], 0) for x in b if x["score"] is None) / float(tot or 1)}]

    def share_ok(d):
        # 22.5% of children 5-17 on 2026-10-01; the map's EJ area is about a third of the city.
        bad = []
        if not 0.15 <= d["ej"] <= 0.40:
            bad.append("%.1f%% of children in EJ blocks, outside 15-40%%" % (100 * d["ej"]))
        if d["unplaced"] > 0.01:
            bad.append("%.1f%% of children in blocks no polygon holds" % (100 * d["unplaced"]))
        return "; ".join(bad) or None
    return [
        Table("ej-communities/polygons", polys, floor=2500, max_drop=0.10, max_growth=1.0, required=["score", "coords"]),
        Each("ej-communities/scores", polys, score_ok, "each polygon's score is 0-30 or 999 (parks and Islais Creek)"),
        extract_read("ej-communities", "polygons"),
        Table("ej-communities/blocks", blocks, floor=5900, max_drop=0.0, key="geoid", required=["geoid", "ej", "hits"]),
        Join("ej-communities blocks~2020 blocks", left=lambda r: None if points(r) is None else [x["geoid"] for x in points(r)],
             right=lambda r: None if blocks(r) is None else [x["geoid"] for x in blocks(r)]),
        Each("ej-communities/ej-flag", blocks, lambda x: None if x["ej"] == (x["score"] is not None and 21 <= x["score"] <= 30)
             else "%s: ej %s with score %s" % (x["geoid"], x["ej"], x["score"]), "ej is exactly score 21-30"),
        Each("ej-communities/share", shares, share_ok, "share of children in EJ blocks in a plausible band; under 1% unplaced"),
    ]


def school_enrolment_checks(root):
    """tools/school-trips/school-enrolment.py: CDE DataQuest enrolment by grade for the case study's public schools."""
    def rows(r):
        d = read_json(r, "data/school-case/enrolment.json")
        return None if d is None else [dict(v, id=k) for k, v in sorted(d["schools"].items())]

    def counted(r):
        x = rows(r)
        return None if x is None else [v for v in x if v.get("total") is not None]

    def ok(v):
        bad = []
        if not 20 <= v["total"] <= 5000:
            bad.append("total %s outside 20 to 5,000" % v["total"])
        s = sum((v.get("grade_pct") or {}).values())
        if abs(s - 100) > 1.5:
            bad.append("grade shares sum to %.1f" % s)
        if not re.match(r"^\d{4}-\d{2}$", v.get("year") or "") or int(v["year"][5:]) != (int(v["year"][:4]) + 1) % 100:
            bad.append("year %r isn't a school year" % v.get("year"))
        elif "year=%s" % v["year"] not in (v.get("url") or ""):
            bad.append("url doesn't name %s" % v["year"])
        return "%s: %s" % (v["id"], "; ".join(bad)) if bad else None

    def drop_ids(r):
        d = read_json(r, "data/school-case/dropoff.json")
        return None if d is None else [s["id"] for s in d["schools"]]
    return [
        Table("school-enrolment/schools", rows, floor=1, max_drop=0.0, key="id", required=["id"]),
        Table("school-enrolment/counted", counted, floor=1, max_drop=0.0, key="id",
              required=["cds", "year", "total", "grade_pct", "url", "read"], dates={"read": ("2026-01-01", "+1")}),
        Join("school-enrolment~dropoff.json", left=drop_ids, right=lambda r: None if rows(r) is None else [v["id"] for v in rows(r)],
             extra_ok=True),
        Each("school-enrolment/plausible", counted, ok,
             "total 20 to 5,000, grade shares sum to 100 within 1.5, a school year the URL names"),
    ]


def school_gravity_checks(root):
    """tools/school-trips/school-gravity.py: CDE's SF schools, SFUSD's requests per seat, and the distance curve's fit to SFCTA's Fig. 5."""
    def city(r):
        d = read_json(r, "data/school-case/enrolment-sf.json")
        return None if d is None else [dict(v, cds=k) for k, v in sorted(d["schools"].items())]

    def rps(r):
        d = read_json(r, "data/school-case/requests-per-seat.json")
        return None if d is None else [dict(x, key="%s|%s|%s" % (x["grade"], x["program"], x["school"])) for x in d["rows"]]

    def fit(r):
        d = read_json(r, "data/school-case/gravity.json")
        return None if d is None else [d["fit"]]

    def city_ok(v):
        t = sum(v["grades"].values())
        if v["total"] < 0 or t > v["total"]:
            return "%s: grades sum to %d of %d" % (v["cds"], t, v["total"])
        return None

    def fit_ok(f):
        bad = []
        for k in ("under1", "1to2", "over2"):
            if abs(f["got"][k] - f["target"][k]) > 3:
                bad.append("%s %.1f against %.1f" % (k, f["got"][k], f["target"][k]))
        if abs(f["got"]["meanMi"] - f["target"]["meanMi"]) > 0.15:
            bad.append("mean %.2f mi against %.2f" % (f["got"]["meanMi"], f["target"]["meanMi"]))
        if not 15000 <= f["students"] <= 30000:
            bad.append("%d SFUSD K-5 students" % f["students"])
        if f["rpsMatched"] < 0.8 * f["schools"]:
            bad.append("only %d of %d schools matched to requests per seat" % (f["rpsMatched"], f["schools"]))
        return "; ".join(bad) or None
    return [
        Table("school-gravity/cde-schools", city, floor=100, max_drop=0.1, key="cds", required=["cds", "name", "total", "grades"]),
        Each("school-gravity/cde-grades", city, city_ok, "each school's grades sum to no more than its total"),
        Table("school-gravity/requests-per-seat", rps, floor=300, max_drop=0.2, key="key", required=["grade", "school", "requests"]),
        Each("school-gravity/fit", fit, fit_ok,
             "the fitted curve's bands within 3 points of SFCTA Fig. 5, its mean within 0.15 mi of 1.40, 15,000 to 30,000 SFUSD K-5 students, "
             "at least 80% of schools matched to a requests-per-seat row"),
    ]


def school_case_checks(root):
    """tools/school-trips/school-case.py: one file per data/school-case/dropoff.json school, each internally consistent and close to the citywide model."""
    def ids(r):
        d = read_json(r, "data/school-case/dropoff.json")
        return None if d is None else [s["id"] for s in d["schools"]]

    def files(r):
        want = ids(r)
        if want is None:
            return None
        out = []
        for i in want:
            d = read_json(r, "site/data/school-case/%s.json" % i)
            if d is not None:
                out.append(d)
        return out

    reg = {}

    def consistent(d):
        bad = []
        if not reg:
            reg.update(read_json(root, "data/school-case/corridor-ids.json") or {"_missing": {}})
        pool = sum(b[2] for b in d["blocks"])
        for k, rows in d["today"].items():
            if len(rows) != len(d["blocks"]):
                bad.append("today[%s] has %d rows for %d blocks" % (k, len(rows), len(d["blocks"])))
            w = sum(b[2] for b, r in zip(d["blocks"], rows) if r and r[0] <= 150)
            if w > pool:
                bad.append("today[%s] within %d > pool %d" % (k, w, pool))
        cc = d.get("comboCheck") or {}
        if cc.get("union", 0) > cc.get("joint", 0):
            bad.append("union %s > joint %s: building everything at once can't reach fewer" % (cc.get("union"), cc.get("joint")))
        # The connector, the zone and their bases: every corridor's gains are keyed by a base that exists.
        bases = d.get("bases") or {}
        kinds = collections.Counter(o["kind"] for o in d["options"])
        if kinds["connector"] != 2 or kinds["zone"] != 1:
            bad.append("want 2 connector options and 1 zone, have %s" % dict(kinds))
        for o in d["options"]:
            if o["kind"] == "corridor":
                if not re.match(r"^c\d+(-\d+)?$", o["id"]):
                    bad.append("corridor id %r isn't c plus a CNN" % o["id"])
                e = reg.get(o["id"]) or {}
                if not e.get("listed") or e.get("cnns") != sorted({str(int(float(c))) for c in o["cnns"]}, key=int):
                    bad.append("corridor %s isn't listed with its blocks in data/school-case/corridor-ids.json" % o["id"])
            for dd, g in (o.get("gains") or {}).items():
                for key in g:
                    if key and key not in bases.get(dd, {}):
                        bad.append("%s gains[%s][%s] has no base" % (o["id"], dd, key))
            for dd, b in (o.get("byDef") or {}).items():
                if not b["onNetwork"] and b["ft"] <= 0 and not b.get("noQuiet"):
                    bad.append("%s %s connector is 0 ft but not on the network" % (o["id"], dd))
                if abs(b.get("protectedFt", 0) + b.get("calmedFt", 0) - b["ft"]) > 1:
                    bad.append("%s %s feet by treatment don't sum to %s" % (o["id"], dd, b["ft"]))
                if b.get("noQuiet") and (bases.get(dd, {}).get(o["id"]) or b["cost"]["central"]):
                    bad.append("%s %s has no quiet route but a gain or a cost" % (o["id"], dd))
        if len({o["id"] for o in d["options"]}) != len(d["options"]):
            bad.append("option ids repeat")
        by_fac = collections.defaultdict(list)
        for o in d["options"]:
            c = o["cost"]
            if not (0 <= c["low"] <= c["central"] <= c["high"]):
                bad.append("%s cost not low <= central <= high: %s" % (o["id"], c))
            if o["kind"] == "corridor" and len(o["facility"]) == 1:
                by_fac[o["facility"][0]].append((o["miles"], c["central"], o["id"]))
        for f, xs in by_fac.items():
            xs.sort()
            for (m0, c0, i0), (m1, c1, i1) in zip(xs, xs[1:]):
                if m1 > m0 and c1 + 0.005 < c0:
                    bad.append("%s %s costs less than %s for more miles" % (f, i1, i0))
        return "%s: %s" % (d["id"], "; ".join(bad[:3])) if bad else None

    def students_sum(d):
        """Each school's expected students, on the blocks in reach plus those beyond, sum to its enrolment within 1%."""
        st = d.get("students")
        if not st:
            return None
        kept = sum(b[4] for b in d["blocks"])
        bad = []
        if abs(kept + st["beyond"] - st["total"]) > 0.01 * st["total"]:
            bad.append("blocks %.1f + beyond %.1f against enrolment %d" % (kept, st["beyond"], st["total"]))
        if st["beyond"] < -0.01 * st["total"]:
            bad.append("negative beyond %.1f" % st["beyond"])
        if any(len(b) < 6 or b[4] < 0 or b[5] <= 0 for b in d["blocks"]):
            bad.append("a block without expected students or a drive time")
        return "%s: %s" % (d["id"], "; ".join(bad)) if bad else None

    def near_citywide(d):
        v = (d.get("model") or {}).get("citywideCheck")
        if not v:
            return None
        bad = []
        p = v.get("pass")
        if p and p["min_min"] < -0.1:
            bad.append("pass 1 faster than pass 2 by %.1f min" % -p["min_min"])
        eff = v.get("doorEffect")
        if eff and not d.get("held") and (abs(eff["median_min"]) > 2 or eff["max_min"] > 5):
            bad.append("door moves times by median %+.1f, max %+.1f min against the repo point" % (eff["median_min"], eff["max_min"]))
        return "%s: %s" % (d["id"], "; ".join(bad)) if bad else None

    return [
        Table("school-case/files", files, floor=1, max_drop=0.0, key="id",
              required=["id", "blocks", "today", "options", "comboCheck", "model"]),
        Join("school-case files~dropoff.json", left=ids,
             right=lambda r: None if files(r) is None else [d["id"] for d in files(r)]),
        Each("school-case/consistent", files, consistent,
             "within <= pool, union <= joint, each cost low <= central <= high and rising with miles per facility, "
             "a connector (protected, calm) and a zone, feet by treatment summing to the connector, no gain without a quiet route, "
             "corridor ids c plus a CNN and listed in corridor-ids.json, every gains key a base"),
        Each("school-case/students", files, students_sum,
             "each school's expected students (tools/school-trips/school-gravity.py) on the blocks in reach plus beyond sum to its enrolment within 1%, "
             "every block carries students and a drive time"),
        Each("school-case/citywide", files, near_citywide,
             "pass 1 no faster than the citywide pass 2; the door moves times by at most 2 min (median) and 5 min (any block), held schools aside"),
    ]


def muni_gtfs_checks(root):
    """tools/muni/muni-gtfs.py: SFMTA's GTFS feed (every core file, and the joins between them) and site/data/muni-schools.json."""
    return _script_module("muni-gtfs").checks(root)


def muni_frequency_checks(root):
    """tools/muni/muni-frequency.py: departures per hour at every Muni stop, and the 1 California's midday headway against SFMTA's page."""
    return _script_module("muni-frequency").checks(root)


def full_map_destinations_checks(root):
    """tools/travel/full-map-destinations.py: every destination type's features and points."""
    return _script_module("full-map-destinations").checks(root)


def full_map_bike_checks(root, rel="out/full-map/bike/access.json", rule="protected"):
    """tools/travel/access-time.py's full-map runs: one nearest point per block and type, on the rule asked for."""
    def blocks(r):
        d = read_json(r, rel)
        return None if d is None else [{"geoid": b["geoid"], "pop": b["pop"], "types": len(b["access"])} for b in d["blocks"]]

    def meta(r):
        d = read_json(r, rel)
        return None if d is None else [{"k": d["k"], "rule": d["parameters"].get("rule"), "types": len(d["types"])}]

    name = "full-map-bike" if rule == "protected" else "full-map-bike-" + rule
    return [
        Table(name, blocks, floor=5000, max_drop=0.02, key="geoid", required=["geoid", "pop"]),
        Each(name + "/run", meta, lambda m: None if m["k"] == 1 and m["rule"] == rule and m["types"] >= 8
             else "k %s, rule %s, %s types" % (m["k"], m["rule"], m["types"]),
             "a --k 1 --rule %s run over all eight destination types" % rule),
        Each(name + "/every-type", blocks, lambda b: None if b["types"] >= 8 else "%s lists %d types" % (b["geoid"], b["types"]),
             "every block lists every type"),
    ]


def full_map_lts_checks(root):
    """tools/travel/full-map-lts.py: the walk network and the all-ages network by Level of Traffic Stress."""
    return _script_module("full-map-lts").checks(root)


def full_map_transit_origins_checks(root):
    """tools/travel/full-map-transit.py --origins: R5's frontage origins per block."""
    return _script_module("full-map-transit").origins_checks(root)


def full_map_checks(root):
    """tools/travel/full-map.py: the full access map's per-block table."""
    return _script_module("full-map").checks(root)


def daily_trips_site_checks(root):
    """tools/travel/daily-trips-site.py: the Daily Trips map's site data, which must reproduce summary.json's counts."""
    return _script_module("daily-trips-site").checks(root)


def school_travel_checks(root):
    """lib/school-travel-time.py: minutes from each block to the nearest school, and the counts over the target."""
    rel, srel = "out/school-travel/blocks.json", "out/school-travel/summary.json"
    rows = rows_of(rel, "blocks")
    kids = records("census-dhc", "p12-blocks")

    def summary(r):
        d = read_json(r, srel)
        return None if d is None else [d]

    def ordered(x):
        # More network can only help: walk >= today >= plan, per level.
        bad = []
        for lvl in ("elementary", "middle", "high"):
            v = x[lvl]
            w, t, p = (99999 if v[k] is None else v[k] for k in ("walk", "today", "plan"))
            if not (w + 0.05 >= t and t + 0.05 >= p):
                bad.append("%s %s walk %s today %s plan %s" % (x["geoid"], lvl, v["walk"], v["today"], v["plan"]))
        return "; ".join(bad) or None

    def counts(d):
        o, c = d["over_target"], d["children"]
        if not (o["walk"]["5-17"] >= o["today"]["5-17"] >= o["plan"]["5-17"]):
            return "over-target counts not ordered walk >= today >= plan: %s" % o
        if c["5-17"] < 70000:
            return "only %d children 5-17" % c["5-17"]
        return None
    def recount(r):
        # The summary's counts, recounted from the per-block minutes.
        d, b = read_json(r, srel), rows(r)
        if d is None or b is None:
            return None
        out = []
        for nk in ("walk", "today", "plan"):
            n = sum(x[band] for x in b for band, lvl in (("a5_9", "elementary"), ("a10_14", "middle"), ("a15_17", "high"))
                    if x[lvl][nk] is None or x[lvl][nk] > 15.0)
            out.append({"net": nk, "blocks": n, "summary": d["over_target"][nk]["5-17"]})
        return out
    return [
        Each("school-travel/recount", recount, lambda x: "%s: blocks.json gives %d, summary %d" % (x["net"], x["blocks"], x["summary"])
             if x["blocks"] != x["summary"] else None, "the summary's over-target counts recount from blocks.json"),
        Table("school-travel/blocks", rows, floor=4500, max_drop=0.02, key="geoid",
              required=["geoid", "lon", "lat", "elementary", "middle", "high"]),
        Join("school-travel blocks~p12 children", left=lambda r: None if kids(r) is None else
             [x["geoid"] for x in kids(r) if x["a5_9"] + x["a10_14"] + x["a15_17"] > 0],
             right=lambda r: None if rows(r) is None else [x["geoid"] for x in rows(r)]),
        Each("school-travel/monotone", rows, ordered, "each block's time falls or holds from walking to today to the plan"),
        Table("school-travel/summary", summary, floor=1, max_drop=None, required=["over_target", "children", "gaps"]),
        Each("school-travel/counts", summary, counts, "children over the target fall from walking to today to the plan"),
    ]


def _whole(rel):
    """A loader: the whole JSON file as one row."""
    def load(r):
        d = read_json(r, rel)
        return None if d is None else [d]
    load.__name__ = rel
    return load


SSC_GROUPS = {"", "on-existing", "on-potential", "one-block-existing", "one-block-potential", "beyond"}


def ssc_map_checks(root):
    """tools/school-trips/ssc-school-map-compare.py: SFMTA's Safe School Connections map, school by school."""
    import csv

    def rows(r):
        p = os.path.join(r, "out/ssc-school-map/compare.csv")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    srel = "out/ssc-school-map/summary.json"

    def row_ok(x):
        bad = []
        if x["sfmta_group"] not in SSC_GROUPS:
            bad.append("group %r" % x["sfmta_group"])
        if not (-122.53 < float(x["lon"]) < -122.35 and 37.70 < float(x["lat"]) < 37.84):
            bad.append("outside San Francisco %s,%s" % (x["lon"], x["lat"]))
        return "%s: %s" % (x["school"], "; ".join(bad)) if bad else None

    def summary_ok(r):
        s, rs = read_json(r, srel), rows(r)
        if s is None or rs is None:
            return None
        return [{"s": s, "n": len(rs), "matched": sum(1 for x in rs if x["sfmta_group"])}]

    def agrees(x):
        s, out = x["s"], []
        if s["our_open_schools"] != x["n"]:
            out.append("summary counts %d schools, compare.csv has %d" % (s["our_open_schools"], x["n"]))
        if s["matched_to_an_sfmta_icon"] != x["matched"]:
            out.append("summary matches %d, compare.csv %d" % (s["matched_to_an_sfmta_icon"], x["matched"]))
        if s["icons_read_total"] != sum(s["icons_read"].values()):
            out.append("icons by group sum to %d of %d" % (sum(s["icons_read"].values()), s["icons_read_total"]))
        if s["georeference"]["pairs"] < 50 or s["georeference"]["median_residual_m"] > 60:
            out.append("georeference %s" % s["georeference"])
        return "; ".join(out) or None
    return [
        Table("ssc-school-map/compare", rows, floor=180, max_drop=0.05, key="school",
              required=["school", "lon", "lat", "our_walk_today", "m_to_our_counted_network"]),
        Each("ssc-school-map/rows", rows, row_ok, "a known SFMTA group, inside San Francisco"),
        Each("ssc-school-map/summary", summary_ok, agrees,
             "the summary's counts recount from compare.csv; the map's georeference holds"),
    ]


def block_length_checks(root):
    """pipeline/sources/sf-block-length.py: the population-weighted typical block."""
    def summary(r):
        d = read_json(r, "out/block-length/summary.json")
        return None if d is None else [d]
    return [
        Table("block-length/summary", summary, floor=1, max_drop=None, required=["pop_weighted_mean_ft", "tracts"]),
        Each("block-length/range", summary, lambda d: "typical block %s ft over %s tracts" % (d["pop_weighted_mean_ft"], d["tracts"])
             if not (300 <= d["pop_weighted_mean_ft"] <= 600 and d["tracts"] >= 200) else None,
             "the typical block is 300-600 ft over at least 200 tracts"),
    ]


def _csv(rel):
    def load(root):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    load.__name__ = rel
    return load


def _month(r):
    return (r.get("month") or "") + "-01" if r.get("month") else None
_month.__name__ = "month"


def muni_delivered_checks(root):
    """tools/muni/muni-ewt/fetch_service_delivered.py: SFMTA's monthly share of scheduled service hours delivered."""
    def share(r):
        return None if 0.2 <= float(r["actual"]) <= 1 else "actual %s" % r["actual"]
    return [Table("muni/service-delivered", _csv("data/muni-ewt/service_delivered.csv"), floor=200, max_drop=0.0,
                  key="month", required=["month", "actual"], dates={_month: ("2001-01-01", "+0")}),
            Each("muni/service-delivered", _csv("data/muni-ewt/service_delivered.csv"), share, "actual between 0.2 and 1")]


def telraam_checks(root):
    """tools/street-safety/telraam-sf.py: residents' Telraam counters in SF, one row per segment found, with its rush-hour figure."""
    rel = "data/extract/telraam/segments.json"
    segs = rows_of(rel, "segments")

    def kept(r):
        d = segs(r)
        return None if d is None else [x for x in d if x.get("kept")]

    def sane(rows):
        bad = [x["id"] for x in rows if not (0 < x["peak"] < 3000 and x["peak_q1"] <= x["peak"] <= x["peak_q3"]
                                              and x["valid_days"] >= 20 and not x.get("fail")
                                              # the smaller direction's share, and the flag hin-cut-through.py reads
                                              and 0 <= x.get("side_share", -1) <= 0.5
                                              and ("one side" in x.get("flags", [])) == (x["side_share"] < 0.02)
                                              and (not x.get("peak_daylight") or (0 < x["peak_daylight"] < 3000
                                                                                  and x.get("daylight_first") and x.get("daylight_last"))))]
        return not bad, "%d kept segments, %d with a peak out of range, a failure or a one-side flag that disagrees with its share: %s" % (len(rows), len(bad), bad[:5])
    return [
        Table("telraam/segments", segs, floor=30, max_drop=0.25, key="id", required=["id", "line", "valid_days", "kept"]),
        Table("telraam/kept", kept, floor=20, max_drop=0.25, key="id",
              required=["id", "peak", "peak_q1", "first", "last"],
              dates={"first": ("2024-06-17", "+1"), "last": ("2024-06-17", "+1")}),
        Rule("telraam/kept-figures", kept, sane),
    ]


def sfpd_crime_checks(root):
    """tools/street-safety/sfpd-person-crimes.py (which also checks its own reads before writing): the newest 12 months of person
    crimes, and every report since 2018 by place, each against a floor and the previous copy."""
    d = "data/extract/sfpd-person-crimes/"
    inc = rows_of(d + "incidents.json")
    as_rows = lambda rel: (lambda r: None if read_json(r, rel) is None else [{"lon": x[0], "lat": x[1], "n": x[2]} for x in read_json(r, rel)])
    return [
        Table("sfpd-crime/incidents", lambda r: None if inc(r) is None else [{"date": x[0], "id": x[4]} for x in inc(r)],
              floor=3000, max_drop=0.2, key="id", required=["date", "id"], dates={"date": ("2017-01-01", "+1")}),
        Table("sfpd-crime/all-places", as_rows(d + "all-places.json"), floor=2000, max_drop=0.2, key=lambda x: (x["lon"], x["lat"]), required=["n"]),
        Table("sfpd-crime/all-years", as_rows(d + "all-years.json"), floor=2000, max_drop=0.2, key=lambda x: (x["lon"], x["lat"]), required=["n"]),
    ]


def street_safety_cards_checks(root):
    """tools/street-safety/street-safety-cards.py: a crash card for every injury crash since 2005, one file per year and map cell.
    The index's years (no year may lose more than 5% of its cards), each complete year's count, and every file it lists
    on disk with that many well-formed cards and none unlisted."""
    rel = "site/data/street-safety/cards/index.json"

    def years(r):
        d = read_json(r, rel)
        return None if d is None else [dict(v, year=y) for y, v in sorted(d["by_year"].items())]

    def reads(r):
        d = read_json(r, rel)
        return None if d is None else [{"table": t, "year": y, "rows": n} for t, ys in sorted(d["reads"].items()) for y, n in sorted(ys.items())]

    def complete(rows):
        newest = max(x["year"] for x in rows)
        low = [x["year"] for x in rows if x["year"] < newest and x["cards"] < 2000]
        return not low, "%d years to %s; complete years under 2,000 cards: %s" % (len(rows), newest, low or "none")

    def files(r):
        d = read_json(r, rel)
        if d is None:
            return None
        base = os.path.join(r, os.path.dirname(rel))
        on_disk = sorted(os.path.relpath(f, base)[:-5] for f in glob.glob(os.path.join(base, "*", "*.json")))
        return [{"index": d["files"], "disk": on_disk, "base": base}]

    def files_ok(rows):
        I, disk, base = rows[0]["index"], rows[0]["disk"], rows[0]["base"]
        bad = ["unlisted " + k for k in disk if k not in I] + ["missing " + k for k in I if k not in disk]
        for k in sorted(set(I) & set(disk)):
            C = json.load(open(os.path.join(base, k + ".json"), encoding="utf-8"))["cards"]
            if len(C) != I[k]:
                bad.append("%s holds %d cards, index says %d" % (k, len(C), I[k]))
            for c, cd in C.items():
                if not (cd.get("hd") and cd.get("pr") and cd.get("g") and isinstance(cd.get("at"), list) and str(cd.get("dt", "")).startswith(k[:4])):
                    bad.append("%s card %s lacks a header, parties, drawing, points or its year" % (k, c))
                    break
        return not bad, "%d files listed, %d on disk; %s" % (len(I), len(disk), "; ".join(bad[:5]) or "all match")

    return [
        Table("street-safety-cards/years", years, floor=21, max_drop=0.0, key="year", required=["year", "cards", "generic"]),
        Rule("street-safety-cards/complete-years", years, complete),
        Table("street-safety-cards/reads", reads, floor=60, max_drop=0.0, key=lambda x: (x["table"], x["year"]), required=["rows"]),
        Rule("street-safety-cards/files", files, files_ok),
    ]


def muni_satisfaction_checks(root):
    """tools/muni/muni-ewt/fetch_satisfaction.py: SFMTA's yearly share of riders rating Muni good or excellent."""
    return [Table("muni/satisfaction", _csv("data/muni-ewt/satisfaction.csv"), floor=15, max_drop=0.0, key="year",
                  required=["year", "good_or_excellent_pct"])]


DELIVERED_MODE_MAX_LAG_DAYS = 75  # our bound: SFMTA had October 2026 whole by 20 November, so a month late is two missed


def muni_delivered_by_mode_checks(root):
    """tools/muni/muni-ewt/fetch_delivered_by_mode.py: SFMTA's share of scheduled service delivered, by mode and month
    (the script checks the table it read before it replaces the file). Here: no mode-month lost, each once, both coach
    modes in every month from 2022 on, shares in range, and the newest month recent enough."""
    import datetime as _dt
    rows = _csv("data/muni-ewt/lever/delivered_by_mode.csv")

    def share(x):
        try:
            return None if 0 <= float(x["delivered"]) <= 1 and int(x["days"]) >= 1 else "%s %s: delivered %s over %s days" % (x["month"], x["mode"], x["delivered"], x["days"])
        except ValueError:
            return "%s %s: delivered %r, days %r" % (x["month"], x["mode"], x["delivered"], x["days"])

    def months(r):
        d = rows(r)
        if d is None:
            return None
        by = collections.defaultdict(set)
        for x in d:
            by[x["month"]].add(x["mode"])
        return [{"month": m, "modes": v} for m, v in sorted(by.items())]

    def coaches(x):
        return None if x["month"] < "2022-01" or {"motor", "trolley"} <= x["modes"] else "%s has %s" % (x["month"], sorted(x["modes"]))

    def newest(r):  # the newest month SFMTA has every day of; the month in progress is written with its days so far
        d = rows(r)
        if d is None:
            return None
        whole = sorted({x["month"] for x in d if x["mode"] == "motor" and x["days"].isdigit() and
                        int(x["days"]) >= calendar.monthrange(int(x["month"][:4]), int(x["month"][5:7]))[1]})
        return [{"month": whole[-1]}] if whole else [{"month": "2014-07"}]

    def fresh(x):
        y, m = int(x["month"][:4]), int(x["month"][5:7])
        end = _dt.date(y + (m == 12), m % 12 + 1, 1) - _dt.timedelta(days=1)
        lag = (_dt.date.fromisoformat(date_today()) - end).days
        return None if lag <= DELIVERED_MODE_MAX_LAG_DAYS else "newest month %s ended %d days ago" % (x["month"], lag)
    return [
        Table("muni/delivered-by-mode", rows, floor=560, max_drop=0.0, key=lambda x: (x["month"], x["mode"]),
              required=["month", "mode", "delivered", "days"], dates={_month: ("2014-07-01", "+0")}),
        Each("muni/delivered-by-mode/share", rows, share, "delivered between 0 and 1 over at least one day"),
        Each("muni/delivered-by-mode/coaches", months, coaches, "motor and trolley coach in every month from 2022"),
        Each("muni/delivered-by-mode/newest-month", newest, fresh,
             "newest whole month ended at most %d days before the run" % DELIVERED_MODE_MAX_LAG_DAYS),
    ]


TIMETABLE_MONTH_LINES = 40  # lines with a weekday gap a month's timetable has (timetable_month.py's own floor)


def muni_timetable_history_checks(root):
    """tools/muni/muni-ewt/timetable_month.py: each line's timetable by month from 511's archive. Here: no line-month
    lost, each once, the newest month with a weekday gap for TIMETABLE_MONTH_LINES lines or more, and gaps in range."""
    rows = _csv("data/muni-ewt/optimizer/timetable_month.csv")

    def gaps(x):
        bad = []
        for k in ("day", "eve", "sat", "sun"):
            if x.get(k) not in ("", None):
                try:
                    if not 1 <= float(x[k]) <= 180:
                        bad.append("%s %s" % (k, x[k]))
                except ValueError:
                    bad.append("%s %r" % (k, x[k]))
        return "%s %s: %s" % (x["line"], x["month"], ", ".join(bad)) if bad else None

    def newest(r):
        d = rows(r)
        if not d:
            return None
        m = max(x["month"] for x in d)
        return [{"month": m, "n": sum(1 for x in d if x["month"] == m and x.get("day") not in ("", None))}]

    def enough(x):
        return None if x["n"] >= TIMETABLE_MONTH_LINES else "%s has a weekday gap for %d lines" % (x["month"], x["n"])
    return [
        Table("muni/timetable-history", rows, floor=3800, max_drop=0.0, key=lambda x: (x["line"], x["month"]),
              required=["line", "month", "weekdays"], dates={_month: ("2022-01-01", "+0")}),
        Each("muni/timetable-history/gaps", rows, gaps, "minutes between buses from 1 to 180"),
        Each("muni/timetable-history/newest-month", newest, enough,
             "the newest month has a weekday gap for %d lines or more" % TIMETABLE_MONTH_LINES),
    ]


def muni_ridership_checks(root):
    """tools/muni/muni-ewt/fetch_ridership.py: SFMTA's average daily boardings by route, month and day type, and its
    own systemwide weekday figure (the script itself checks the two agree to 1% before writing)."""
    def rows(r):
        d = _csv("data/muni-ewt/ridership.csv")(r)
        return None if d is None else d

    def weekday(r):
        d = rows(r)
        if d is None:
            return None
        by = collections.Counter()
        for x in d:
            if x["day"] == "Weekday":
                by[x["month"]] += float(x["boardings"])
        return [{"month": m, "weekday": v} for m, v in sorted(by.items())]

    def published(r):
        return _csv("data/muni-ewt/weekday_boardings_published.csv")(r)
    return [
        Table("muni/ridership", rows, floor=10000, max_drop=0.02, key=lambda x: (x["month"], x["route"], x["day"]),
              required=["month", "route", "day", "boardings"], dates={_month: ("2019-01-01", "+0")}),
        Table("muni/ridership-published", published, floor=60, max_drop=0.0, key="month", required=["month", "weekday"]),
        Join("muni/ridership-published~ridership weekday months",
             left=lambda r: None if published(r) is None else [x["month"] for x in published(r) if x["month"] >= "2019-01"],
             right=lambda r: None if weekday(r) is None or published(r) is None else
             [x["month"] for x in weekday(r) if x["month"] <= max(p["month"] for p in published(r))]),
    ]


def muni_511_checks(root):
    """tools/muni/muni-ewt/vm_local.sh: the 511 summaries the Muni pages read. The newest month must be the last one 511
    can have posted: the archive is monthly and posts a month in the first days of the next, so the figures end at
    most about 40 days before the run (a month plus 8 days), never 8 days as a live feed would."""
    months = _csv("data/muni-ewt/extract_months.csv")
    import datetime as _dt

    def fresh(r):
        end = _dt.date(int(r["month"][:4]), int(r["month"][5:]), 1)
        end = (end.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
        return None if (_dt.date.today() - end).days <= 40 else "ends %s, %d days ago" % (end, (_dt.date.today() - end).days)

    def newest(r):
        d = months(r)
        return None if d is None else [x for x in d if x["month"] == max(y["month"] for y in d)]

    def per_month(sub, suffix):
        def load(r):
            d = months(r)
            if d is None:
                return None
            have = [x["month"] for x in d if x["month"] >= "2022-01" and x["check"] == "ok"
                    and os.path.exists(os.path.join(r, "data", "muni-ewt", sub, x["month"] + suffix))]
            return [{"month": m} for m in have]
        load.__name__ = "data/muni-ewt/%s/*%s" % (sub, suffix)
        return load
    return [
        Table("muni/extract-months", months, floor=50, max_drop=0.0, key="month", required=["month", "kept_share"],
              dates={_month: ("2019-01-01", "+0")}),
        Table("muni/extract", _csv("data/muni-ewt/extract.csv"), floor=100000, max_drop=0.05),
        Each("muni/newest-month", newest, fresh, "newest month ends within 40 days of the run"),
        Table("muni/stops-months", per_month("stops", ".csv"), floor=45, max_drop=0.0),
        Table("muni/daily-months", per_month("daily", ".csv"), floor=45, max_drop=0.0),
        Table("muni/ontime-months", per_month("ontime", "-stops.csv"), floor=45, max_drop=0.0),
        # each month's stop-level excess wait by clock hour (ewt_stop_hours.py), the line pages' heat maps
        Table("muni/stophours-months", per_month("stophours", ".csv.gz"), floor=45, max_drop=0.0),
        # each line's miles and hours by month and hour (speed_line_month.py --by-hour), the Lines page's speed by hour
        Table("muni/speed-line-hour", _csv("data/muni-ewt/summary_trip/speed_line_hour.csv"), floor=40000, max_drop=0.02,
              key=lambda x: (x["route"], x["month"], x["hr"]), required=["route", "month", "hr", "miles", "obs_hr"],
              dates={_month: ("2019-01-01", "+0")}),
        Each("muni/speed-line-hour-hours", _csv("data/muni-ewt/summary_trip/speed_line_hour.csv"),
             lambda x: None if 5 <= int(x["hr"]) <= 22 and float(x["obs_hr"]) >= 0 and float(x["miles"]) >= 0 else "hour or total out of range",
             "hour 5 to 22, miles and hours not negative"),
    ]


def sfmta_crowding_checks(root):
    """tools/muni/muni-ewt/sfmta_crowding.py: SFMTA's published percent of trips crowded, by route and month (the script
    itself checks values and months before writing)."""
    return [Table("muni/sfmta-crowding", _csv("data/muni-ewt/optimizer/sfmta_crowding.csv"), floor=2500, max_drop=0.0,
                  key=("route", "route_name", "month"), required=["route", "month", "pct"])]


def muni_rt_checks(root):
    """tools/muni/muni-ewt/rt_daily.py: the Muni daily figures rebuilt from the realtime archive for the days 511's
    monthly stop records don't cover yet. The newest day with figures must be at most RT_MAX_AGE_DAYS old (Bryan,
    2026-11-12: "Daily"), each day once, each with a timetable edition and a read date, every day with status ok in
    the per-line file and nothing there that days.csv doesn't list, and the citywide figure of each day plausible."""
    import datetime as _dt
    days = _csv("data/muni-ewt/rt/days.csv")

    def daily_rows(r):
        rows = []
        for p in sorted(glob.glob(os.path.join(r, "data", "muni-ewt", "rt", "daily", "20??-??.csv"))):
            with open(p, encoding="utf-8", newline="") as fh:
                rows += list(csv.DictReader(fh))
        return rows if rows or days(r) is not None else None
    daily_rows.__name__ = "data/muni-ewt/rt/daily/*.csv"

    def ok_days(r):
        d = days(r)
        return None if d is None else [x for x in d if x["status"] == "ok"]

    def newest(r):
        d = ok_days(r)
        return None if d is None else [max(d, key=lambda x: x["sdate"])] if d else [{"sdate": ""}]

    def fresh(x):
        if not x["sdate"]:
            return "no archive day has status ok"
        age = (_dt.date.today() - _dt.date(int(x["sdate"][:4]), int(x["sdate"][4:6]), int(x["sdate"][6:]))).days
        # Only the VM can refresh these (rt_daily.py exits 0 elsewhere), so off it the copy in the repo is held to
        # the monthly files' 40 days and a laptop run doesn't stop on data it couldn't have updated.
        limit = RT_MAX_AGE_DAYS if os.path.isdir(os.path.expanduser("~/muni-511/history")) else 40
        return None if age <= limit else "newest day %s is %d days old (limit %d)" % (x["sdate"], age, limit)

    def status(x):
        return None if x["status"] in ("ok", "outage", "failed") else "%s: status %r" % (x["sdate"], x["status"])

    def coverage(x):
        if x["status"] != "ok":
            return None  # an outage or failed day carries no figures; the newest-day check covers a run of them
        share = float(x["visits_rebuilt"] or 0) / max(float(x["visits_scheduled"] or 0), 1)
        if x["status"] == "ok" and share < 0.5:
            return "%s: status ok with %.0f%% of stop visits rebuilt" % (x["sdate"], 100 * share)
        if int(x["trips_scheduled"] or 0) < 3000:
            return "%s: only %s trips scheduled (timetable edition %s)" % (x["sdate"], x["trips_scheduled"], x["gtfs"])
        return None

    def citywide(r):
        rows = daily_rows(r)
        if rows is None:
            return None
        acc = {}
        for x in rows:
            a = acc.setdefault(x["sdate"], [0.0] * 6)
            eb, eba = float(x["eb"] or 0), float(x["eba"] or 0)
            if x["swt"] and eb:
                a[0] += float(x["swt"]) * eb; a[1] += eb
            if x["awt"] and eba:
                a[2] += float(x["awt"]) * eba; a[3] += eba
            if x["miles"] and float(x["obs_hr"] or 0):
                a[4] += float(x["miles"]); a[5] += float(x["obs_hr"])
        return [{"sdate": k, "ewt": (a[2] / a[3] - a[0] / a[1]) if a[1] and a[3] else None,
                 "mph": a[4] / a[5] if a[5] else None} for k, a in sorted(acc.items())]
    citywide.__name__ = "citywide by day"

    def plausible(x):
        if x["ewt"] is None or not 0.0 <= x["ewt"] <= 6.0:
            return "%s: citywide excess wait %s minutes" % (x["sdate"], x["ewt"])
        if x["mph"] is None or not 4.0 <= x["mph"] <= 15.0:
            return "%s: citywide speed %s mph" % (x["sdate"], x["mph"])
        return None

    def rt_date(r):
        return "%s-%s-%s" % (r["sdate"][:4], r["sdate"][4:6], r["sdate"][6:]) if r.get("sdate") else None
    rt_date.__name__ = "sdate"
    return [
        Table("muni-rt/days", days, floor=1, max_drop=0.0, key="sdate",
              required=["sdate", "status", "read", ("gtfs", 0.5), ("visits_scheduled", 0.5), ("visits_rebuilt", 0.5)],
              dates={rt_date: ("2026-11-10", "+0"), "read": ("2026-11-01", "+0")}),
        Each("muni-rt/status", days, status, "status is ok, outage or failed"),
        Each("muni-rt/coverage", days, coverage, "an ok day rebuilt half its stop visits or more, on a full timetable"),
        Each("muni-rt/newest-day", newest, fresh, "newest day with figures is at most %d days old on the VM" % RT_MAX_AGE_DAYS),
        Table("muni-rt/daily", daily_rows, floor=20, max_drop=0.05, key=lambda x: (x["route"], x["sdate"]),
              required=["route", "sdate"], dates={rt_date: ("2026-11-10", "+0")}),
        Join("muni-rt/days~daily", left=lambda r: None if ok_days(r) is None else [x["sdate"] for x in ok_days(r)],
             right=lambda r: None if daily_rows(r) is None else sorted({x["sdate"] for x in daily_rows(r)})),
        Each("muni-rt/citywide", citywide, plausible, "each day's citywide excess wait 0-6 min and speed 4-15 mph"),
    ]


RT_MAX_AGE_DAYS = 2


def muni_crowding_checks(root):
    """tools/muni/muni-ewt/crowding_update.py: how full Muni buses are, from SFMTA's live occupancy levels in our realtime
    archive (crowding_by_hour.py, crowding_levels.py). The newest complete service day must be at most
    CROWDING_MAX_AGE_DAYS old on the VM (SF_REFRESH_TODAY sets the day, to watch it fail) (40 off it, where the step can't refresh), the level counts must add up to the
    reads on every row, and the two files must agree on reads and crowded reads, line by line and hour by hour."""
    import datetime as _dt
    import json as _json
    by_hour = _csv("data/muni-ewt/optimizer/crowding_by_hour.csv")
    levels = _csv("data/muni-ewt/optimizer/crowding_levels_hour.csv")
    along = _csv("data/muni-ewt/optimizer/crowding_levels_along.csv")
    LV = ("empty", "many_seats", "few_seats", "standing_room", "crushed", "full", "not_accepting")

    def days(r):
        p = os.path.join(r, "data", "muni-ewt", "optimizer", "crowding_levels.json")
        if not os.path.exists(p):
            return None
        d = _json.load(open(p, encoding="utf-8"))["complete_days"]
        return [{"sdate": max(d["weekday"] + d["weekend"], default="")}]
    days.__name__ = "data/muni-ewt/optimizer/crowding_levels.json"

    def fresh(x):
        if not x["sdate"]:
            return "no complete service day"
        age = (_dt.date.fromisoformat(date_today()) - _dt.date(int(x["sdate"][:4]), int(x["sdate"][4:6]), int(x["sdate"][6:]))).days
        vm = os.path.isdir(os.path.expanduser(os.environ.get("MUNI_511_ROOT", "~/muni-511") + "/history"))
        limit = CROWDING_MAX_AGE_DAYS if vm else 40
        return None if age <= limit else "newest complete day %s is %d days old (limit %d)" % (x["sdate"], age, limit)

    def adds_up(x):
        n = sum(int(x[k]) for k in LV)
        return None if n == int(x["reads"]) else "%s %s %s: levels add to %d, reads %s" % (x["line"], x["direction"], x.get("hour", x.get("tenth")), n, x["reads"])

    def pairs(r):
        a, b = by_hour(r), levels(r)
        if a is None or b is None:
            return None
        k = lambda x: (x["line"], x["direction"], x["day_type"], x["hour"])
        aa, bb = {k(x): x for x in a}, {k(x): x for x in b}
        return [{"key": key, "a": aa.get(key), "b": bb.get(key)} for key in sorted(set(aa) | set(bb))]
    pairs.__name__ = "crowding_by_hour~crowding_levels_hour"

    def agree(x):
        a, b = x["a"], x["b"]
        if a is None or b is None:
            return "%s: in %s only" % (x["key"], "crowding_levels_hour.csv" if a is None else "crowding_by_hour.csv")
        crowded = sum(int(b[c]) for c in ("standing_room", "crushed", "full", "not_accepting"))
        if int(a["reads"]) != int(b["reads"]) or int(a["crowded_reads"]) != crowded:
            return "%s: %s of %s crowded by hour, %d of %s in levels" % (x["key"], a["crowded_reads"], a["reads"], crowded, b["reads"])
        return None

    return [
        Table("muni-crowding/by-hour", by_hour, floor=1000, max_drop=0.5, key=lambda x: (x["line"], x["direction"], x["day_type"], x["hour"]),
              required=["line", "day_type", "hour", "reads", "crowded_reads"]),
        Table("muni-crowding/levels-hour", levels, floor=1000, max_drop=0.5, key=lambda x: (x["line"], x["direction"], x["day_type"], x["hour"]),
              required=["line", "day_type", "hour", "reads"] + list(LV)),
        Table("muni-crowding/levels-along", along, floor=300, max_drop=0.5, key=lambda x: (x["line"], x["direction"], x["tenth"]),
              required=["line", "tenth", "reads"] + list(LV)),
        Each("muni-crowding/newest-day", days, fresh, "newest complete service day is at most %d days old on the VM" % CROWDING_MAX_AGE_DAYS),
        Each("muni-crowding/levels-add-up", levels, adds_up, "each row's level counts add up to its reads"),
        Each("muni-crowding/along-adds-up", along, adds_up, "each tenth's level counts add up to its reads"),
        Each("muni-crowding/files-agree", pairs, agree, "both files hold the same reads and crowded reads"),
    ]


OPTIMIZER_MAX_LAG_DAYS = 40  # the muni/newest-month bound: 511 posts a month's stop records early in the next one


def muni_optimizer_newest(root):
    """(path, parsed) of the newest month's results file under site/data/muni-optimizer/, or (None, None)."""
    files = sorted(glob.glob(os.path.join(root, "site", "data", "muni-optimizer", "20??-??.json")))
    if not files:
        return None, None
    try:
        with open(files[-1], encoding="utf-8") as f:
            return files[-1], json.load(f)
    except (OSError, ValueError):
        return files[-1], None


def muni_optimizer_checks(root):
    """tools/muni/muni-ewt/optimizer_build.py: Upgrade a Bus Line's results for the newest month. The script checks its
    own arithmetic before it writes (the dashboard's waits, costs, the grid, the map); these check the file it left:
    every line there with its figures in range, one grid value per combination, the month the dashboard's newest, and
    that month recent enough."""
    import datetime as _dt

    def head(r):
        path, d = muni_optimizer_newest(r)
        return None if d is None else [dict({k: v for k, v in d.items() if k != "lines"}, _file=os.path.basename(path), _n=len(d.get("lines") or {}))]

    def lines(r):
        _path, d = muni_optimizer_newest(r)
        return None if d is None else [dict(x, line=l) for l, x in sorted((d.get("lines") or {}).items())]

    def grid_ok(x):
        n = 1
        for f in x["fixes"]:
            n *= len(f["units"])
        g = x["grid"]
        bad = [k for k in ("gain", "walk") if len(g.get(k) or []) != n]
        # low, middle and high; a figure the line doesn't have (no wait figure, no crowding from SFMTA) ships no series
        want = {"wait": x["today"].get("wait") is not None, "mph": True, "crowd": x["today"].get("crowd") is not None}
        for k, has in want.items():
            if g.get(k) is None:
                if has:
                    bad.append(k + " missing")
            elif len(g[k]) != 3 or any(case is not None and len(case) != n for case in g[k]):
                bad.append(k)
        return "line %s: %s not three cases of %d combinations" % (x["line"], ", ".join(bad), n) if bad else None

    def today_ok(x):
        t = x["today"]
        bad = []
        if t.get("mph") is None or not 3 <= t["mph"] <= 20:
            bad.append("mph %s" % t.get("mph"))
        if t.get("wait") is not None and not 1 <= t["wait"] <= 30:
            bad.append("wait %s" % t["wait"])
        if t.get("wait") is not None and abs(t["swt"] + t["ewt"] - t["wait"]) > 0.02:
            bad.append("wait %s is not timetable %s plus excess %s" % (t["wait"], t["swt"], t["ewt"]))
        if t.get("crowd") is not None and not 0 <= t["crowd"] <= 1:
            bad.append("crowd %s" % t["crowd"])
        return "line %s: %s" % (x["line"], ", ".join(bad)) if bad else None

    def month_ok(h):
        muni = read_json(root, "site/data/muni.json") or {}
        want = (((muni.get("windows") or {}).get("90") or {}).get("monthList") or [None])[-1]
        if h["_file"] != h.get("month", "") + ".json":
            return "%s holds month %s" % (h["_file"], h.get("month"))
        # the month before passes too: the build waits there until the new month's timetable and delivered share are
        #   in (optimizer_build.waiting_on), and the newest-month check below bounds how long
        prev = None if not want else "%04d-%02d" % ((int(want[:4]), int(want[5:7]) - 1) if want[5:7] != "01" else (int(want[:4]) - 1, 12))
        return None if h.get("month") in (want, prev) else "results are for %s, the dashboard's newest month is %s" % (h.get("month"), want)

    def date_ok(h):
        read = h.get("sourcesRead") or {}
        if not read or h.get("dataUpdated") != min(read.values()):
            return "dataUpdated %s is not the older of %s" % (h.get("dataUpdated"), read)
        return None if h["dataUpdated"] <= date_today() else "dataUpdated %s is after today" % h["dataUpdated"]

    def fresh(h):
        y, m = int(h["month"][:4]), int(h["month"][5:7])
        end = _dt.date(y + m // 12, m % 12 + 1, 1) - _dt.timedelta(days=1)
        age = (_dt.date.fromisoformat(date_today()) - end).days
        return None if age <= OPTIMIZER_MAX_LAG_DAYS else "newest month %s ended %d days ago" % (h["month"], age)

    return [
        Table("muni-optimizer/lines", lines, floor=45, max_drop=0.05, key="line",
              required=["today", "fixes", "grid", "history", "map", "schedule", "hours"]),
        Each("muni-optimizer/grid", lines, grid_ok, "every grid series has one value per combination of the fixes' units"),
        Each("muni-optimizer/today", lines, today_ok,
             "speed 3 to 20 mph; expected wait absent or 1 to 30 min and the sum of its two parts; crowded share absent or 0 to 1"),
        Each("muni-optimizer/month", head, month_ok, "the newest file is named for its month, and that month is the dashboard's newest or the one before"),
        Each("muni-optimizer/data-updated", head, date_ok, "dataUpdated is the older of the dates its sources were read, and not after today"),
        Each("muni-optimizer/newest-month", head, fresh, "newest month ended at most %d days before the run" % OPTIMIZER_MAX_LAG_DAYS),
    ]


CROWDING_MAX_AGE_DAYS = 2


SPECS = {
    "socrata": Spec(["data/socrata-cache/%s-*.json" % f for f in SOCRATA], socrata_checks(SOCRATA),
                    "DataSF rowsUpdatedAt, to the second",
                    "every cached query of a dataset whose rows changed since the query was read",
                    "pipeline/refresh-socrata.py <ids> (always incremental)"),
    "extracts": Spec(["data/extract/%s/*.json" % s for s in ("sfmta-bikeway", "sfmta-bci", "slow-streets",
                                                             "census-blocks", "libraries", "cpad")],
                     extracts_checks,
                     "ArcGIS row count plus newest last_edited_date (bikeway); row count, largest key and the "
                     "layer's dataLastEditDate (BCI); DataSF rowsUpdatedAt (slow streets, 2020 blocks, libraries); CPAD's row count and release name",
                     "the whole extract of a source whose marker moved",
                     "pipeline/refresh-extracts.py (always incremental)"),
    "mirror:bos": mirror_spec("mirror:bos", "bos-meetings", "bos-meetings", 1500,
                              "Legistar's meeting calendar for each year since 2019",
                              "meetings not yet final (no minutes and under 45 days old) and meetings not held"),
    "mirror:public-works": mirror_spec("mirror:public-works", "public-works-commission", "public-works-commission", 70,
                                       "the Granicus view's meeting listing; for the delegated contract reports, the "
                                       "commission calendar page's list of agenda PDFs",
                                       "meetings not yet final, and new ones; agenda PDFs the calendar newly lists, "
                                       "and reports no agenda had linked",
                                       extra=delegated_checks(),
                                       paths=["data/public-works-commission/delegated.json"]),
    "mirror:rec-park": mirror_spec("mirror:rec-park", "rec-park-commission", "rec-park-commission", 85,
                                   "the Granicus view's meeting listing", "meetings not yet final, and new ones"),
    "mirror:sfcta": mirror_spec("mirror:sfcta", "sfcta-board", "sfcta-board", 150,
                                "the Granicus views' meeting listings", "meetings not yet final, and new ones"),
    "mirror:sfmta-board": mirror_spec("mirror:sfmta-board", "sfmta-board", "sfmta-board", 160,
                                      "the Granicus view's meeting listing",
                                      "meetings not yet final, and new ones; from disk, every meeting read by an older "
                                      "minutes parser",
                                      extra=minutes_checks("sfmta-board", "fetch-sfmta-board.py", 150,
                                                           consent=re.compile(r"(?i)^\s*(?:consent calendar|all matters "
                                                                              r"listed hereunder constitute a consent calendar)"),
                                                           minutes_cache="sfmta-board-minutes")),
    "mirror:sfmta-hearings": mirror_spec("mirror:sfmta-hearings", "sfmta-hearings", "sfmta-hearings", 130,
                                         "sfmta.com's hearing archive listing (10 pages)",
                                         "hearings whose results order is not yet read, and new ones"),
    "mirror:sfpuc": mirror_spec("mirror:sfpuc", "sfpuc-commission", "sfpuc-commission-granicus", 160,
                                "the Granicus view's meeting listing",
                                "meetings not yet final, and new ones; from disk, every meeting read by an older "
                                "minutes parser",
                                # Set at today's level: 25 of 184 consent items read no vote from
                                # the 2024-05 and 2024-06 minutes, and the 2026-07-28 calendar's
                                # items sit under "Report of the General Manager" in the extract.
                                extra=minutes_checks("sfpuc-commission", "fetch-sfpuc-commission.py", 170,
                                                     undecided=0.15, empty=0.02)),
    "upcoming-meetings": Spec([UPCOMING_REL], upcoming_checks,
                              "each body's own listing, re-read every run, since a meeting not yet held has no "
                              "change marker (bounded: meetings dated after today to 90 days out)",
                              "every listing, and each listed meeting's page or agenda in that window; nothing held",
                              "tools/meetings/upcoming-meetings.py --update"),
    "sfmta-projects": Spec(["out/sfmta-projects/projects.json", "out/sfmta-projects/projects.geojson",
                            "out/sfmta-projects/projects.md", "data/sfmta-pages/**"],
                           sfmta_projects_checks,
                           "ArcGIS row count, newest LAST_EDITED_DATE and CREATED_DATE per layer; DataSF "
                           "rowsUpdatedAt for the two mirrors; sfmta.com sitemap lastmod per project page",
                           "a layer or mirror whose marker moved (held copies in .cache/sfmta-projects/); a project "
                           "page only when the sitemap says it changed",
                           "tools/projects/sfmta-projects.py --update"),
    "sfmta-project-pages": Spec(["out/sfmta-projects/pages.json", "data/extract/sfmta-pages/*.json",
                                 "data/sfmta-pages/**"],
                                sfmta_pages_checks, "sfmta.com sitemap lastmod per page",
                                "pages edited after our copy was taken",
                                "tools/projects/sfmta-project-pages.py --sitemap --update"),
    "sfmta-page-dates": Spec(["out/sfmta-page-dates/*"], page_dates_checks,
                             "each page's text: the hash of the request built from the page copy the "
                             "sfmta-project-pages step keeps (itself re-read on the sitemap's lastmod)",
                             "Jev is asked only about new pages and pages whose request hash changed",
                             "tools/projects/sfmta-page-dates.py --update"),
    "sfmta-hearings": Spec(["data/extract/sfmta-hearings/*.json", "out/sfmta-hearings/*",
                            ".cache/sfmta-hearings/**"],
                           hearings_checks, "the archive listing (a new hearing appears there); bounded re-read of hearings under 60 days old",
                           "the archive listing and each hearing page under 60 days old; held PDFs are kept",
                           "tools/meetings/sfmta-hearings.py --update"),
    "sfmta-board-records": Spec(["data/extract/sfmta-board/*.json", "out/sfmta-board/*", ".cache/sfmta-board/**"],
                                board_checks, "the Granicus meeting listing and sfmta.com minutes index; bounded re-read of agendas under 60 days old",
                                "the meeting listing, the minutes index, and agendas under 60 days old or never read",
                                "tools/meetings/sfmta-board-records.py --update"),
    "bos-street-records": Spec(["out/bos-records/*", ".cache/bos-records/**"], bos_checks,
                               "Legistar's search has no change date: bounded re-read of this year and last, at most daily",
                               "this year's and last year's searches for each of the 24 phrases",
                               "tools/meetings/bos-street-records.py --update"),
    "sfpuc-commission": Spec(["data/extract/sfpuc-commission/*.json", "out/sfpuc-commission/*",
                              ".cache/sfpuc-commission/**"],
                             sfpuc_checks, "the minutes log page's list of PDF links",
                             "the log page, and only minutes PDFs not read before",
                             "tools/meetings/sfpuc-commission.py --update"),
    "dpw-projects": Spec(["data/extract/dpw-projects/*.json", "out/dpw-projects/*", "data/dpw-cache/**"],
                         dpw_checks, "the project index (re-read every run); pages have no sitemap, Last-Modified or ETag, so a bounded re-read at 7 days",
                         "the project index every run, and each page whose copy is over 7 days old",
                         "tools/projects/dpw-projects.py --update"),
    "sf-mode-share": Spec(["data/extract/census-acs/*.json", "site/data/mode-share.json"], mode_share_checks,
                          "whether the Census API answers for the next ACS 1-year release",
                          "the whole B08301 series, when a new year is published",
                          "tools/travel/sf-mode-share.py --update"),
    "osm-walk-network": Spec(["data/osm-cache/sf-walk.json"], walk_checks,
                             "Overpass count of walkable ways edited since the copy's base timestamp",
                             "the whole city's walkable ways, when any was edited or the copy is 30 days old",
                             "tools/travel/osm-walk-network.py --update"),
    "osm-drive-network": Spec(["data/osm-cache/sf-drive.json"], drive_checks,
                              "Overpass count of drivable ways (or their nodes) edited since the copy's base timestamp",
                              "the whole city's drivable ways, when any was edited or the copy is 30 days old",
                              "tools/travel/osm-drive-network.py --update"),
    "census-block-outlines": Spec(["data/extract/census-blocks/outlines-*.json"], outline_checks,
                                  "the vintage: a decennial release (2010, 2020) never changes once "
                                  "published, so a vintage on disk is current by definition",
                                  "a vintage missing from disk; nothing once both are held", "pipeline/sources/census-block-outlines.py --update"),
    "census-children": Spec(["data/extract/census-dhc/*.json"], census_children_checks,
                            "the vintage: the 2020 DHC is a final decennial release, so a table on disk is current by definition",
                            "a table missing from disk; nothing once it is held", "tools/school-trips/census-children.py --update"),
    "supervisor-districts": Spec(["site/data/supervisor-districts.json"], supervisor_districts_checks,
                                 "DataSF rowsUpdatedAt for cqbw-m5m3, against the one recorded in the file",
                                 "all 11 simplified outlines when rowsUpdatedAt moved; nothing otherwise",
                                 "pipeline/sources/supervisor-districts.py --update"),
    "sf-address-points": Spec(["site/data/sf-addresses.json"], sf_address_points_checks,
                              "DataSF rowsUpdatedAt for 3mea-di5p, against the one recorded in the file",
                              "every address point when rowsUpdatedAt moved; nothing otherwise",
                              "pipeline/sources/sf-address-points.py --update"),
    "school-points": Spec(["data/school-sim/school-points.json"], school_points_checks,
                          "DataSF rowsUpdatedAt for 3mea-di5p, against the one recorded in the file; the CDE file is a fixed archive capture",
                          "every address point when rowsUpdatedAt moved; nothing otherwise",
                          "tools/school-trips/school-points.py --update"),
    "ej-communities": Spec(["data/extract/ej-communities/*.json"], ej_communities_checks,
                           "DataSF rowsUpdatedAt for y6ci-vpnb, against the one recorded with the extract",
                           "the whole map (2,702 polygons) when rowsUpdatedAt moved; the block join every run, from disk",
                           "pipeline/sources/ej-communities.py --update"),
    "muni-511": Spec(["data/muni-ewt/**"], muni_511_checks,
                     "a month directory on the VM gains DONE when 511 has posted the month and it was extracted",
                     "new months from 511; on the VM, months whose inputs or scripts changed are rebuilt",
                     "tools/muni/muni-ewt/vm_local.sh (on the VM)"),
    "muni-rt-daily": Spec(["data/muni-ewt/rt/**"], muni_rt_checks,
                          "the newest service date whose buses have all run (12:30 UTC the next day), against the "
                          "archive days already built; a day built from raw snapshots is re-read once the archive's "
                          "compacted Parquet for it appears",
                          "only the new or changed days from the archive bucket, then the excess-wait and "
                          "speed scripts over that month's archive days; 511's Muni timetable at most weekly",
                          "tools/muni/muni-ewt/rt_daily.py --update (on the VM)"),
    "muni-crowding": Spec(["data/muni-ewt/optimizer/crowding_by_hour.*", "data/muni-ewt/optimizer/crowding_levels*"],
                          muni_crowding_checks,
                          "the bucket's compacted day files (one a UTC day, written at 01:30 UTC and never replaced): a "
                          "file new to the cache or whose size changed",
                          "only the new or changed day files; then the newest four weeks re-summarised (a few seconds)",
                          "tools/muni/muni-ewt/crowding_update.py --update (on the VM)"),
    "muni-service-delivered": Spec(["data/muni-ewt/service_delivered.csv", "data/muni-ewt/service_delivered_target.json"],
                                   muni_delivered_checks,
                                   "DataSF kc49-udxn rowsUpdatedAt",
                                   "measure 441's every month, when the marker moved",
                                   "tools/muni/muni-ewt/fetch_service_delivered.py --update"),
    "muni-ridership": Spec(["data/muni-ewt/ridership.csv", "data/muni-ewt/weekday_boardings_published.csv"],
                           muni_ridership_checks,
                           "SFMTA's Tableau download carries no change marker, so the bound is the whole file",
                           "the whole CSV (about 1 MB) every run, written only when its rows differ",
                           "tools/muni/muni-ewt/fetch_ridership.py --update"),
    "sfmta-crowding": Spec(["data/muni-ewt/optimizer/sfmta_crowding.csv", "data/muni-ewt/optimizer/sfmta_crowding_read.json"],
                           sfmta_crowding_checks,
                           "SFMTA's Tableau download carries no Last-Modified or ETag, so the bound is the whole file",
                           "the whole CSV (about 110 KB) every run, written only when its rows differ",
                           "tools/muni/muni-ewt/sfmta_crowding.py --update"),
    "muni-delivered-by-mode": Spec(["data/muni-ewt/lever/delivered_by_mode.csv"], muni_delivered_by_mode_checks,
                                   "SFMTA's transtat view carries no Last-Modified or ETag, so the bound is the whole table",
                                   "the whole CSV (about 1 MB) every run, written only when its rows differ",
                                   "tools/muni/muni-ewt/fetch_delivered_by_mode.py --update"),
    "muni-timetable-history": Spec(["data/muni-ewt/optimizer/timetable_month.csv"], muni_timetable_history_checks,
                                   "a DONE file under ~/muni-511/history/regional-<month>-so-sf on the VM, for a month "
                                   "later than the tracked file's newest",
                                   "only the months the tracked file lacks; none off the VM",
                                   "pipeline/venv-step.py tools/muni/muni-ewt/timetable_month.py --update"),
    "muni-optimizer": Spec(["site/data/muni-optimizer/*.json"], muni_optimizer_checks,
                           "none: a build step, run when its inputs change", "nothing fetched",
                           "pipeline/venv-step.py tools/muni/muni-ewt/optimizer_build.py"),
    "sfpd-crime": Spec(["data/extract/sfpd-person-crimes/*"], sfpd_crime_checks,
                       "DataSF rowsUpdatedAt for wg3w-h783, against the one recorded in meta.json",
                       "the newest 12 months and this year's and recent years' reports when it moved; older years from a cache of at most 90 days",
                       "tools/street-safety/sfpd-person-crimes.py --update"),
    "street-safety-cards": Spec(["site/data/street-safety/cards/**", "data/socrata-cache/street-safety-cards/*"],
                                street_safety_cards_checks,
                                "DataSF rowsUpdatedAt, to the second, for each of ubvf-ztfx, 8gtc-pjc6 and nwes-mmgh",
                                "on a change, this year's and last year's queries of each table, and an older year's once its "
                                "copy is 90 days old; then only the card files whose inputs hash differently",
                                "tools/street-safety/street-safety-cards.py --update"),
    "street-safety-crashes": Spec(["data/socrata-cache/street-safety/*"],
                                  socrata_checks(STREET_SAFETY_CRASHES, cache="data/socrata-cache/street-safety"),
                                  "DataSF rowsUpdatedAt, to the second, for each of nwes-mmgh, 8gtc-pjc6, ubvf-ztfx and dau3-4s8f",
                                  "every query in lib/street_safety_reads.py QUERIES with no held copy, and on a "
                                  "change every query of that table",
                                  "tools/street-safety/street-safety-crashes.py --update"),
    "telraam": Spec(["data/extract/telraam/segments.json"], telraam_checks,
                    "Telraam publishes no change marker, so the bound is time: closed three-month chunks are kept, the open "
                    "one is re-read once per window end, and a snapshot every 14 days finds new segments",
                    "each segment's open chunk (the 3 months holding today), and every chunk of a segment not seen before",
                    "tools/street-safety/telraam-sf.py --update"),
    "muni-satisfaction": Spec(["data/muni-ewt/satisfaction.csv"], muni_satisfaction_checks,
                              "SFMTA's Tableau download carries no change marker, so the bound is the whole file",
                              "the whole CSV (about 200 bytes) every run, written only when its rows differ",
                              "tools/muni/muni-ewt/fetch_satisfaction.py --update"),
    "muni-gtfs": Spec([".cache/muni-gtfs/*", "site/data/muni-schools.json"], muni_gtfs_checks,
                      "Last-Modified and ETag from one HEAD request on the feed zip, against the held copy's; "
                      "the zip's SHA-256 when they move",
                      "the whole zip (about 10 MB) when either marker moved, kept only if its bytes differ and it passes; the school file every run, from disk",
                      "tools/muni/muni-gtfs.py --update"),
    "school-enrolment": Spec(["data/school-case/enrolment.json"], school_enrolment_checks,
                             "none published: DataQuest is asked for each public school's years after the one held, "
                             "up to the school year containing today",
                             "at most two pages a school, a year at a time; a year that parses replaces the held copy",
                             "tools/school-trips/school-enrolment.py --update"),
    "school-gravity": Spec(["data/school-case/enrolment-sf.json", "data/school-case/requests-per-seat.json", "data/school-case/gravity.json"],
                           school_gravity_checks,
                           "none published: CDE's file for each school year after the one held; the highlights page's newest Main Round",
                           "one file a school year (about 32 MB, county 38 kept) and one PDF a Main Round, only when newer",
                           "tools/school-trips/school-gravity.py --update"),
    "school-case": Spec(["site/data/school-case/*"], school_case_checks,
                        "none: a build step, run when its inputs change", "nothing fetched",
                        "tools/school-trips/school-case.py"),
    "school-travel-time": Spec(["out/school-travel/*"], school_travel_checks,
                               "none: a build step, run when its inputs change", "nothing fetched",
                               "lib/school-travel-time.py"),
    "ssc-school-map-compare": Spec(["out/ssc-school-map/*"], ssc_map_checks,
                                   "none: a build step, run when its inputs change; SFMTA's map image is a fixed picture, fetched once into .cache/ssc-map/",
                                   "the image only when the cache is missing",
                                   "pipeline/venv-step.py tools/school-trips/ssc-school-map-compare.py"),
    "sf-block-length": Spec(["out/block-length/*"], block_length_checks,
                            "none: a build step, run when its inputs change", "nothing fetched",
                            "pipeline/sources/sf-block-length.py"),
    "walk-reach": Spec(["site/data/bike-history/walk-reach.json"], walk_reach_checks,
                       "none: a build step, run when its inputs change", "nothing fetched",
                       "tools/bike-network/walk-reach.py"),
    "osm-sfmta-compare": Spec(["data/osm-cache/*", "out/osm-compare/*", "data/socrata-cache/ygmz-vaxd-*.json"],
                              osm_checks, "Overpass count of bikeway ways edited since the copy's base timestamp",
                              "the whole city's bikeway ways, when any was edited or the copy is 30 days old",
                              "tools/travel/osm-sfmta-compare.py --update"),
    "street-work-list": Spec(["out/street-work/*", ".cache/street-work/*"] +
                             ["data/socrata-cache/%s-*.json" % f for f in ("btxj-k9uh", "ygmz-vaxd", "5wbp-dwzt")],
                             street_work_checks,
                             "DataSF rowsUpdatedAt (through the shared cache); ArcGIS row count, largest OBJECTID "
                             "and row counts by the three priority fields for the modal priority layer, plus a re-read at 30 days",
                             "the priority layer when its marker moved; DataSF as the socrata step left it",
                             "tools/projects/street-work-list.py --update"),
    "department-project-pages": Spec(["out/department-pages/*", "data/extract/sfpuc-projects/*", "data/dept-pages-cache/**"],
                                     dept_pages_checks,
                                     "each department's sitemap (re-read every run); pages have no Last-Modified or ETag, so a bounded re-read at 7 days",
                                     "the department sitemaps every run, and each page whose copy is over 7 days old",
                                     "tools/projects/department-project-pages.py --update"),
    "dept-page-dates": Spec(["out/dept-page-dates/*"], dept_page_dates_checks,
                            "each page's text: the hash of the request built from the page copy the dpw-projects "
                            "and department-project-pages steps keep (each re-read at 7 days)",
                            "Jev is asked only about new pages and pages whose request hash changed",
                            "tools/projects/sfmta-page-dates.py --pages departments --update"),
    # Build steps: they fetch nothing, so no marker; their checks run on what
    # they wrote, and a failure puts the previous files back and stops every
    # later step (pipeline/transportation-update.py).
    # The full access map. Its Muni minutes, out/full-map/transit.json, are computed on a
    # sim VM (scripts/full-map-transit-vm.sh) and committed; tools/travel/full-map-transit.py --check runs their checks.
    "muni-frequency": Spec(["out/full-map/muni-stops.json"], muni_frequency_checks,
                           "none: a build step, run when the held GTFS zip changes", "nothing fetched",
                           "tools/muni/muni-frequency.py"),
    "full-map-destinations": Spec(["data/full-map/destinations.json"], full_map_destinations_checks,
                                  "none: a build step; its DataSF reads go through the socrata step", "nothing fetched",
                                  "pipeline/venv-step.py tools/travel/full-map-destinations.py"),
    "full-map-bike": Spec(["out/full-map/bike/*"], full_map_bike_checks,
                          "none: a build step, run when its inputs change", "nothing fetched",
                          "pipeline/venv-step.py tools/travel/access-time.py --dests data/full-map/destinations.json "
                          "--rule protected --nets today --k 1 --out out/full-map/bike"),
    "full-map-bike-furth1": Spec(["out/full-map/bike-furth1/*"],
                                 lambda root: full_map_bike_checks(root, "out/full-map/bike-furth1/access.json", "furth1"),
                                 "none: a build step, run when its inputs change", "nothing fetched",
                                 "pipeline/venv-step.py tools/travel/access-time.py --dests data/full-map/destinations.json "
                                 "--rule furth1 --nets today --k 1 --out out/full-map/bike-furth1"),
    "full-map-lts": Spec(["out/full-map/lts.json"], full_map_lts_checks,
                         "none: a build step, run when its inputs change", "nothing fetched",
                         "pipeline/venv-step.py tools/travel/full-map-lts.py"),
    "full-map-transit-origins": Spec(["data/full-map/transit-origins.json"], full_map_transit_origins_checks,
                                     "none: a build step, run when its inputs change", "nothing fetched",
                                     "pipeline/venv-step.py tools/travel/full-map-transit.py --origins"),
    "full-map": Spec(["out/full-map/blocks.json", "out/full-map/summary.json"], full_map_checks,
                     "none: a build step, run when its inputs change", "nothing fetched",
                     "pipeline/venv-step.py tools/travel/full-map.py"),
    "daily-trips-site": Spec(["site/data/daily-trips.json"], daily_trips_site_checks,
                             "none: a build step, run when its inputs change", "nothing fetched",
                             "tools/travel/daily-trips-site.py"),
    "coordination-projects": Spec(["site/data/coordination.json", "out/coordination/*", "data/project-ids.json"],
                                  coordination_checks, "none: a build step, run when its inputs change",
                                  "nothing fetched", "tools/projects/coordination-projects.py"),
    "bike-removals": Spec(["site/data/bike-history/removed.json"], removals_checks,
                          "none: a build step, run when its inputs change", "nothing fetched",
                          "tools/bike-network/bike-removals.py"),
    "department-overlap": Spec(["site/data/department-overlap.json"], overlap_checks,
                               "none: a build step, run when its inputs change", "nothing fetched",
                               "tools/projects/department-overlap.py"),
    "collect-transportation": Spec([".cache/site-socrata/*", "site/data/transportation.json"], site_socrata_checks,
                                   "DataSF rowsUpdatedAt per dataset",
                                   "the whole dataset (paged to the count DataSF reports) when its marker moved",
                                   "site/scripts/collect-transportation.mjs (always incremental)"),
}


def check(step, root=ROOT, prev_root=None):
    spec = SPECS[step]
    return run(spec.checks(root), root, prev_root)


# What each source step keeps, named as its publisher names it, for the inventory.
SOURCE_NAMES = {
    "socrata": "DataSF: 3psu-pn9h Streets (centerlines), 5wbp-dwzt Utility Excavation Moratorium Streets, "
               "78va-8dhi Historical Pavement Condition Index, 7e7j-59qk Schools, 9ivs-nf5y On-Street Parking "
               "Census, abhw-ffzx Mid-Block Traffic Calming Areas, bp3t-bd4t Intersection-Level Traffic Calming "
               "Devices, btxj-k9uh Public Works coordination feed, i28k-bkz6 Muni Stops, ygmz-vaxd MTA Bike "
               "Network (DataSF copy)",
    "extracts": "SFMTA ArcGIS bikeway layer (rows and geometry); SFMTA 2023 draft Bike Comfort Index; DataSF "
                "hkz3-itiu Slow Streets, p2fw-hsrv Census 2020 blocks, nc68-ngbr City Facilities (libraries); CPAD units (non-Rec-and-Park open space)",
    "mirror:bos": "Board of Supervisors and committee agendas, Legistar",
    "mirror:public-works": "Public Works Commission agendas and delegated contract reports, Granicus",
    "mirror:rec-park": "Recreation and Park Commission agendas, Granicus",
    "mirror:sfcta": "SFCTA Board and Vision Zero Committee agendas, Granicus",
    "mirror:sfmta-board": "SFMTA Board agendas (Granicus) and minutes (sfmta.com)",
    "mirror:sfmta-hearings": "SFMTA engineering public hearings, sfmta.com",
    "mirror:sfpuc": "SFPUC Commission agendas (Granicus) and minutes",
    "upcoming-meetings": "Meetings not yet held at those bodies, and SFMTA events",
    "sfmta-projects": "SFMTA Multimodal/projects ArcGIS layer; DataSF 6ibt-jpn7 and j4dm-6zyr (its stale mirrors)",
    "sfmta-project-pages": "Every /projects/ page in sfmta.com's sitemap",
    "sfmta-page-dates": "Construction and consultation dates read off those pages by TypeSafe's Jev",
    "sfmta-hearings": "SFMTA hearing agendas and Directive Order PDFs (bike items)",
    "sfmta-board-records": "SFMTA Board agendas and minutes (bike items)",
    "bos-street-records": "Legistar file search, 24 street phrases per year since 2019",
    "sfpuc-commission": "SFPUC Commission minutes PDFs",
    "dpw-projects": "Public Works project pages (sfpublicworks.org)",
    "sf-mode-share": "Census ACS 1-year B08301, San Francisco commute mode",
    "osm-sfmta-compare": "OpenStreetMap bikeway ways in San Francisco (Overpass)",
    "osm-walk-network": "OpenStreetMap walkable ways in San Francisco (Overpass)",
    "osm-drive-network": "OpenStreetMap drivable ways in San Francisco (Overpass)",
    "census-block-outlines": "Census 2010 and 2020 block outlines (TIGERweb)",
    "census-children": "Census 2020 DHC table P12, children by block (data.census.gov)",
    "school-enrolment": "CDE DataQuest, Enrollment by Grade, school level, for the case study's public schools",
    "school-gravity": "CDE Census Day enrolment files (cdenroll), every SF school; SFUSD's annual assignment highlights (requests per seat)",
    "ej-communities": "SF Planning's Environmental Justice Communities map, DataSF y6ci-vpnb",
    "school-points": "Addresses with Units - Enterprise Addressing System, DataSF 3mea-di5p, for CDE's school street addresses",
    "supervisor-districts": "Current Supervisor Districts, DataSF cqbw-m5m3",
    "sf-address-points": "Addresses with Units - Enterprise Addressing System, DataSF 3mea-di5p",
    "muni-gtfs": "SFMTA GTFS Transit Data (muni_gtfs-current.zip), scheduled Muni service",
    "muni-511": "511 SF Bay historic stop observations, Muni, monthly (processed on the VM)",
    "muni-service-delivered": "Controller's scorecard measures, DataSF kc49-udxn, measure 441 (SFMTA service hours delivered)",
    "sfpd-crime": "DataSF wg3w-h783, Police Department Incident Reports: 2018 to Present",
    "street-safety-crashes": "DataSF nwes-mmgh, 8gtc-pjc6, ubvf-ztfx (Traffic Crashes Resulting in Injury: victims, parties, crashes) and dau3-4s8f (Vision Zero fatality log), the Street Safety map's and the injury pages' queries",
    "street-safety-cards": "DataSF ubvf-ztfx, 8gtc-pjc6 and nwes-mmgh (Traffic Crashes Resulting in Injury: crashes, parties, victims), one query a year from 2005",
    "telraam": "Telraam API v1 (telraam-api.net): residents' window traffic counters in SF, hourly per segment",
    "muni-satisfaction": "SFMTA, Customer rating: Overall customer satisfaction with Muni (transtat.sfmta.com)",
    "muni-ridership": "SFMTA, Average Daily Muni Boardings by Route and Month (transtat.sfmta.com); DataSF kc49-udxn measure 428",
    "sfmta-crowding": "SFMTA, Percent of daily Muni trips crowded by route and month (transtat-public.sfmta.com CrowdingbyRoute.csv)",
    "muni-rt-daily": "511 GTFS-realtime Vehicle Positions and Trip Updates for Muni, as saved by our archive "
                     "(tools/muni/rt-archive/), and 511's Muni GTFS timetable (operator_id=SF)",
    "muni-crowding": "SFMTA's live occupancy level on each Muni bus, in 511 GTFS-realtime Vehicle Positions as saved by "
                     "our archive (tools/muni/rt-archive/)",
    "street-work-list": "DataSF coordination feed, bikeway and moratorium (shared cache); SFMTA modal priority layer",
    "department-project-pages": "SFPUC, Public Works and search pages for each coordination-feed job",
    "dept-page-dates": "Dates read off Public Works and SFPUC project pages by TypeSafe's Jev",
    "collect-transportation": "DataSF 5wbp-dwzt, btxj-k9uh, hkz3-itiu, abhw-ffzx, bp3t-bd4t, read by the site's collector",
}

# Sources the pages read that no source step re-reads, because they are fixed
# releases or hand-kept. Each has a check that says when a newer edition or a
# changed page makes it stale; adopting one is a decision, so it is reported
# (status newer-release in sources.json, printed by the audit's F3) or fails
# its step, never taken silently.
# (source, change marker, what happens when it moves, where the check runs)
FIXED = [
    ("Six Wayback captures of DataSF ygmz-vaxd (2021-03-25 to 2026-04-05)",
     "the capture's timestamp: an archived capture never changes",
     "nothing to re-read; the present comes from the live ArcGIS layer (extracts)",
     "tools/bike-network/bike-network-history.py (SNAPSHOT_CAPTURES), fixed"),
    ("Census 2010 blocks (TIGERweb), used for 2010 to 2019 reach",
     "the vintage: a decennial release never changes",
     "nothing to re-read",
     "pipeline/refresh-extracts.py lists it as a fixed release"),
    ("Census ACS 5-year block-group population (B01003)",
     "whether the year after the newest in ACS_YEARS answers on the Census API",
     "reported as release:acs5-bg newer-release; adopting it is a decision",
     "pipeline/refresh-extracts.py"),
    ("California Department of Education private schools file",
     "whether the Wayback Machine holds a capture newer than the file in use",
     "reported as release:cde-schools newer-release",
     "pipeline/refresh-extracts.py"),
    ("Biking and Rolling Plan PDFs: the plan (class definitions), Appendix L (North Star index), North Star map (trace)",
     "each PDF's file name and byte length from one HEAD request, against the copy the builds read",
     "reported as release:biking-rolling-plan newer-release; re-run plan-class-definitions.py, north-star-index.py "
     "or north-star-map-trace.py on the new file",
     "pipeline/refresh-extracts.py"),
    ("SFMTA Travel Decisions Survey reports 2015 to 2021 (mode share)",
     "whether sfmta.com answers for a report page of a later survey year (HEAD, one per year)",
     "reported as release:travel-decisions-survey newer-release; its figures are entered by hand",
     "pipeline/refresh-extracts.py"),
    ("Hand-written project summaries (site/data/bike-history/project-summaries.json)",
     "every phrase a summary quotes, against its page's current teaser and text",
     "the step fails until the summary is re-read, so a changed page cannot leave a stale quote on a card",
     "tools/bike-network/bike-reported-work.py (build, reruns when the pages change)"),
    ("Hand-curated built and planned work (REPORTED, PLANNED in tools/bike-network/bike-reported-work.py)",
     "each entry's quoted words, against its page's current text",
     "the step fails until the entry is re-read",
     "tools/bike-network/bike-reported-work.py"),
]


def is_build(spec):
    return spec.marker.startswith("none: a build step")


def cell(t):
    return str(t).replace("|", "\\|")


def inventory():
    lines = ["| Source | Updater | Change marker | What an update re-reads | Quality checks |",
             "| --- | --- | --- | --- | --- |"]
    for step, spec in SPECS.items():
        if is_build(spec):
            continue
        kinds = collections.Counter(re.sub(r"\[.*", "", r.check).rsplit(".", 1)[-1] for r in check(step))
        lines.append("| %s | `%s` (step `%s`) | %s | %s | %d: %s |" % (
            cell(SOURCE_NAMES[step]), spec.flag, step, cell(spec.marker), cell(spec.reread), sum(kinds.values()),
            ", ".join("%s %d" % (k, v) for k, v in sorted(kinds.items()))))
    for name, marker, reread, where in FIXED:
        lines.append("| %s | `%s` | %s | %s | fixed or hand-kept |" % (cell(name), where, cell(marker), cell(reread)))
    return "\n".join(lines)


def inventory_problems(steps):
    """What --inventory --check fails on: a source step of the orchestrator's STEPS with no row, or a row saying none."""
    problems = ["source step %s has no inventory row" % n for n, kind, *_ in steps
                if kind in ("source", "node") and n not in SPECS and n != "collect-osm-compare"]
    for line in inventory().splitlines()[2:]:
        if re.search(r"\|\s*none\b", line, re.I):
            problems.append("row says none: " + line[:120])
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--inventory" in sys.argv:
        print(inventory())
        if "--check" in sys.argv:
            import importlib.util
            upd = paths.load("transportation-update.py")
            problems = inventory_problems(upd.STEPS)
            for p in problems:
                print("FAIL", p, file=sys.stderr)
            sys.exit(1 if problems else 0)
        return
    unknown = set(args) - set(SPECS)
    if unknown:
        sys.exit("no checks for: %s" % ", ".join(sorted(unknown)))
    failed = 0
    for step in args or SPECS:
        res = check(step)
        bad = [r for r in res if not r.ok]
        failed += len(bad)
        print("%-26s %3d checks, %d failed" % (step, len(res), len(bad)))
        for r in (res if "--verbose" in sys.argv else bad):
            print("    %r" % r)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
