#!/usr/bin/env python3
"""Re-read the tracked extracts behind the bike pages only when their source has changed.

    pipeline/refresh-extracts.py            # check every source, re-read the changed ones
    pipeline/refresh-extracts.py --force    # re-read every live source

The bike pages build from extracts under data/extract/ that
tools/bike-network/bike-progress.py and tools/bike-network/bike-network-history.py fill on
--refetch. Those flags re-read everything, which takes minutes. This checks
each live source with one small request first and re-reads only what moved:

  source                       change marker
  sfmta-bikeway network+geom   ArcGIS: row count and newest last_edited_date
  sfmta-bci scores             ArcGIS: row count, largest cnn key, dataLastEditDate
  slow-streets, census 2020,   DataSF: the dataset's rowsUpdatedAt
  libraries
  cpad sf-units                ArcGIS: statewide row count plus the release the
                               layer's description names (scripts/cpad-sf.py)

A re-read that returns the records already on disk leaves the file as it was
(lib/extract.py), so a run with no new data changes nothing tracked.

Some extracts are fixed releases that never change: the six Wayback captures
of the bikeway layer (history; the present comes from the live layer), Census
2010 blocks, and the dated CDE schools file. For the releases that do get
newer editions, this checks whether one has appeared and says so without
adopting it, because adopting a new edition changes a published figure's
basis and is a decision:

  ACS 5-year population        is the year after the newest in ACS_YEARS out?
  CDE schools file             is there a Wayback capture newer than ours?
  Biking and Rolling Plan      does each PDF sfmta.com serves (the plan, its
    PDFs                       appendix, the North Star map) still have the
                               name and byte length of the copy the builds
                               read? One HEAD request each.
  Travel Decisions Survey      is there a report page for a survey year after
                               the newest tools/travel/sf-mode-share.py enters?
                               One HEAD request per later year.

Each check is recorded in data/pipeline-state/sources.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from extract import Extract  # noqa: E402
from lib import bikeway_departed, pipeline_state  # noqa: E402


def load(name):
    return paths.load(name + ".py")


def get_json(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def arcgis_marker(service, date_field=None, key_field=None):
    """Row count plus the newest edit date (or largest key), and the layer's own last data edit.

    A layer with no edit-date field (the BCI scores) moves its count and
    largest key only when rows are added or removed; a re-scored block moves
    neither. Hosted layers publish `editingInfo.dataLastEditDate`, which does
    move, so it is part of the marker wherever the service gives one.
    """
    stats = [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "n"}]
    if date_field:
        stats.append({"statisticType": "max", "onStatisticField": date_field, "outStatisticFieldName": "m"})
    if key_field:
        stats[0]["onStatisticField"] = key_field
        stats.append({"statisticType": "max", "onStatisticField": key_field, "outStatisticFieldName": "m"})
    q = urllib.parse.urlencode({"where": "1=1", "outStatistics": json.dumps(stats), "f": "json"})
    d = get_json("%s/query?%s" % (service, q))
    # Services differ on the case of the output names ("n" or "N").
    a = {k.lower(): v for k, v in d["features"][0]["attributes"].items()}
    if a.get("n") is None:
        raise RuntimeError("no row count in the statistics answer: %s" % json.dumps(d)[:200])
    marker = "%s rows, max %s" % (a.get("n"), a.get("m"))
    edited = (get_json("%s?f=json" % service).get("editingInfo") or {}).get("dataLastEditDate")
    return marker + (", data edited %s" % edited if edited else "")


def reread(source, key, produce, meta_fn=None):
    """Re-read one extract with the meta it already carries, or meta_fn()'s where the meta names a release that
    moves with the data (CPAD); True when the file changed.

    A re-read with fewer than half the records on disk is a failed read, not a
    smaller layer: it raises, and the extract on disk is left as it was.
    """
    ex = Extract(source)
    old = ex.read(key)
    before = old.fetched_on if old else None
    path = ex.path(key)
    mtime = os.path.getmtime(path) if os.path.exists(path) else None
    records = produce()
    if old is not None and len(records) < len(old.records) // 2:
        raise RuntimeError("%s/%s re-read returned %d records against %d on disk"
                           % (source, key, len(records), len(old.records)))
    ex.write(key, records, meta=(meta_fn() if meta_fn else old.meta if old else None))
    return mtime is None or os.path.getmtime(path) != mtime or before is None


def check(name, marker_fn, rereads, force):
    """Compare a source's marker with the last run's; re-read its extracts when it moved.

    The new marker is recorded only once every re-read has succeeded. A failed
    re-read records the source as failed with no marker, so the next run reads
    it again instead of taking the change as read.
    """
    try:
        marker = marker_fn()
    except Exception as e:  # noqa: BLE001
        pipeline_state.record(name, "failed", detail="marker check failed: %s" % e)
        print("  %s: CHECK FAILED (%s); extracts left as they are" % (name, e))
        return
    last = pipeline_state.load().get(name, {})
    if marker == last.get("version") and last.get("status") != "failed" and not force:
        pipeline_state.record(name, "unchanged", version=marker)
        print("  %s: unchanged (%s)" % (name, marker))
        return
    changed = []
    for source, key, produce, *meta_fn in rereads:
        try:
            if reread(source, key, produce, *meta_fn):
                changed.append("%s/%s" % (source, key))
        except Exception as e:  # noqa: BLE001
            pipeline_state.record(name, "failed", detail="re-read of %s/%s failed: %s" % (source, key, e))
            print("  %s: RE-READ FAILED for %s/%s (%s); the extract on disk is kept" % (name, source, key, e))
            return
    pipeline_state.record(name, "changed" if changed else "unchanged", version=marker,
                          detail="re-read; changed: %s" % (", ".join(changed) or "none"))
    print("  %s: %s -> re-read, %s" % (name, marker, ("changed " + ", ".join(changed)) if changed else "no difference"))


def newer_release(name, probe):
    try:
        found = probe()
    except Exception as e:  # noqa: BLE001
        pipeline_state.record(name, "failed", detail=str(e))
        print("  %s: CHECK FAILED (%s)" % (name, e))
        return
    pipeline_state.record(name, "newer-release" if found else "unchanged", detail=found or "no newer release")
    print("  %s: %s" % (name, ("NEWER RELEASE AVAILABLE: " + found) if found else "no newer release"))


# The plan's three PDFs: (marker name, URL, the copy the builds read, the byte
# length to expect when no copy is kept). The plan itself is 92 MB and not
# kept; its length is as sfmta.com served it on 2026-09-30, under the file
# name "San Francisco Biking and Rolling Plan 2025 FINAL.pdf".
PLAN_PDFS = [
    ("plan", "https://www.sfmta.com/media/41810/download", None, 96237342),
    ("appendix", "https://www.sfmta.com/media/41946/download", ".cache/north-star-appendix/appendix.pdf", None),
    ("north-star-map", "https://www.sfmta.com/media/41812/download", ".cache/north-star-map/northstar-map.pdf", None),
]
TDS_REPORT = "https://www.sfmta.com/reports/travel-decision-survey-%d"


def head(url, timeout=60):
    """Status and headers of `url` without its body; a 404 is an answer, not an error."""
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "Mozilla/5.0 (sf-works; +https://sf-works.org)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, fh.headers
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 404, e.headers
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    prog = load("bike-progress")
    hist = load("bike-network-history")

    def layer_keeping_departed():
        """The live layer, after recording each row it no longer has, with the line the extract on disk gives it
        (lib/bikeway_departed.py). Runs before the network and geometry extracts are replaced."""
        old_net, old_geo = Extract("sfmta-bikeway").read("network"), Extract("sfmta-bikeway").read("geometry")
        rows = prog.fetch_layer()
        if old_net is not None:
            added = bikeway_departed.record(old_net.records, rows, old_geo.records if old_geo else [],
                                            dt.date.today().isoformat())
            if added:
                print("  sfmta-bikeway: %d row(s) left the layer, kept in %s: OBJECTID %s"
                      % (len(added), os.path.relpath(bikeway_departed.PATH, ROOT), ", ".join(map(str, added))))
        return rows

    check("arcgis:sfmta-bikeway", lambda: arcgis_marker(prog.SERVICE, date_field="last_edited_date"),
          [("sfmta-bikeway", "network", layer_keeping_departed), ("sfmta-bikeway", "geometry", hist.fetch_geometry)],
          args.force)
    check("arcgis:sfmta-bci", lambda: arcgis_marker(hist.BCI_SERVICE, key_field="cnn_sgmt_pkey"),
          [("sfmta-bci", "scores", hist.fetch_bci)], args.force)
    cpad = load("cpad-sf")
    check("arcgis:cpad-sf", lambda: "%s; %s" % (arcgis_marker(cpad.SERVICE), cpad.release()),
          [("cpad", "sf-units", cpad.fetch_units, cpad.meta)], args.force)
    for fxf, source, key, produce in [(hist.SLOW_STREETS_ID, "slow-streets", "segments", hist.fetch_slow_streets),
                                      (hist.BLOCKS_2020_ID, "census-blocks", "2020", hist.fetch_blocks_2020),
                                      (hist.FACILITIES_ID, "libraries", "branches", hist.fetch_libraries)]:
        check("socrata:" + fxf, lambda fxf=fxf: str(sfdata.metadata(fxf)["rows_updated_ts"]),
              [(source, key, produce)], args.force)

    def acs_probe():
        y = max(hist.ACS_YEARS) + 1
        try:
            d = get_json(hist.CEDSCI % y, timeout=60)
            if d.get("response", {}).get("data"):
                return "ACS 5-year %d is published; bike-network-history.py reads through %d" % (y, y - 1)
        except Exception:  # noqa: BLE001 - an unpublished year answers with an error
            pass
        return None
    newer_release("release:acs5-bg", acs_probe)

    def cde_probe():
        url = hist.CDE_CAPTURE.split("id_/", 1)[1]
        rows = get_json("https://web.archive.org/cdx/search/cdx?url=%s&output=json&from=%s"
                        % (urllib.parse.quote(url, safe=""), hist.CDE_FILE_DATE.replace("-", "")), timeout=60)
        newer = [r[1] for r in rows[1:] if r[1][:8] > hist.CDE_FILE_DATE.replace("-", "")]
        return ("a CDE schools capture dated %s is newer than the %s file in use" % (newer[-1][:8], hist.CDE_FILE_DATE)
                if newer else None)
    newer_release("release:cde-schools", cde_probe)

    def plan_probe():
        moved = []
        for name, url, copy, length in PLAN_PDFS:
            status, h = head(url)
            if status != 200:
                raise RuntimeError("%s answered HTTP %s" % (url, status))
            want = os.path.getsize(os.path.join(ROOT, copy)) if copy and os.path.exists(os.path.join(ROOT, copy)) else length
            got = int(h.get("Content-Length") or -1)
            if got != want:
                moved.append("%s is now %s bytes (%s), the builds read %s" % (
                    name, got, h.get("Content-Disposition", "").split("filename=")[-1].strip('"') or url, want))
        return "; ".join(moved) or None
    newer_release("release:biking-rolling-plan", plan_probe)

    def tds_probe():
        newest = max(s["year"] for s in load("sf-mode-share").SURVEYS)
        import datetime as dt
        found = [y for y in range(newest + 1, dt.date.today().year + 1) if head(TDS_REPORT % y)[0] == 200]
        return ("sfmta.com has a Travel Decisions Survey report for %s; tools/travel/sf-mode-share.py enters surveys "
                "through %d" % (", ".join(map(str, found)), newest)) if found else None
    newer_release("release:travel-decisions-survey", tds_probe)


if __name__ == "__main__":
    main()
