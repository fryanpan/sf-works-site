"""Fetch and cache every input the crash street-context build reads, asking each source whether it changed first.

    from street_sources import load_all
    src = load_all(update=False)   # cached copies only; reads a source cold when no copy is held
    src = load_all(update=True)    # ask each source for its change marker, re-read only what moved

Two kinds of source:

  The crash table (ubvf-ztfx) comes from ../crash_tables.py's held copy, refreshed there by `data_updated_at`
  (with update=True, unless CRASH_TABLES_HELD says ../crash-augment.py already refreshed it this run).

  DataSF (Socrata), every other table. Read through lib/sfdata.py into data/socrata-cache/crash-augment-street/ (gitignored), one cache
  file per query, each carrying the date its rows were read. With update=True the dataset's `rowsUpdatedAt` is asked
  (one small request); a held query is re-read only when that marker differs from the one recorded at the last
  read (data/socrata-cache/crash-augment-street/_markers.json), or when the held rows no longer hash to what that
  read wrote. A re-read shorter than 90% of the held copy raises, so a short read never replaces good rows.

  ArcGIS feature layers. Read page by page into .cache/crash-augment/street/<name>.json (gitignored), with the
  marker the layer gave at read time. The marker is the layer's `editingInfo.dataLastEditDate` plus its row count
  where the layer publishes one. SFMTA's lane layer (MTA.CTA_trafficlanes) publishes no edit date and its
  LAST_EDITED_DATE column is empty, so with update=True it gets a bounded re-read: the whole layer, attributes only
  (15,444 rows, 16 requests), kept only when it passes the same 90% floor.

A failed re-read keeps the held copy, records the source as failed in data/pipeline-state/sources.json under
"crash-street:<name>", and the build carries on with the held copy. A source with no held copy that cannot be read
stops the build. Without update=True no network request is made when every copy is held, so a rerun is offline.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import json
import os
import urllib.parse

import sfdata  # noqa: E402  (lib/ is on sys.path once lib.paths is imported)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # crash_tables.py
from lib import pipeline_state  # noqa: E402
from lib.fetch import read as http_read  # noqa: E402

ROOT = paths.ROOT
SOCRATA_CACHE = os.path.join(ROOT, "data", "socrata-cache", "crash-augment-street")
ARCGIS_CACHE = os.path.join(ROOT, ".cache", "crash-augment", "street")
MARKER_PREFIX = "crash-street:"
# A re-read must hold at least this share of the held copy's rows, or it is treated as a failed read.
REREAD_FLOOR = 0.90

# The crash table itself (ubvf-ztfx) is not read here: it comes from ../crash_tables.py, the held copy every lane of
# crash-augment builds on, so the street and vehicle columns describe the same crashes.
CRASH_COLUMNS = ["case_id_pkey", "collision_date", "collision_severity", "intersection", "cnn_intrsctn_fkey",
                 "cnn_sgmt_fkey", "primary_rd", "secondary_rd", "tb_latitude", "tb_longitude"]
CRASH_FLOOR = 60000

# name -> (dataset id, $select, floor on a cold read). Each select names only the columns the build reads.
SOCRATA = {
    "streets": ("3psu-pn9h", "cnn,streetname,classcode,f_node_cnn,t_node_cnn,active,line", 16000),
    "speed_limits": ("3t7b-gebn", "cnn,speedlimit,install_date,mtab_date,status", 15000),
    "safety_zones": ("vtn2-q8ky", "cnn,units,install_da,status", 250),
    "cameras": ("d5uh-bk84", "site_id,location,date,point", 10000),
    "traffic_calming": ("abhw-ffzx", "row_id,cnn,tc_measure,install_datetime,current_status", 1500),
    "slow_streets": ("hkz3-itiu", "cnn,streetname,status,install_date", 200),
    "signals": ("ybh5-27n2", "cnn,type,startyear", 1400),
}

# name -> (layer URL, query parameters, floor, has an edit-date marker)
ARCGIS = {
    "epc": ("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/"
            "draft_equity_priority_communities_pba2050plus_acs2022a/FeatureServer/0",
            {"where": "tract_geoid LIKE '06075%'", "outFields": "tract_geoid,epc_2050p,epc_class",
             "returnGeometry": "true", "outSR": "4326", "orderByFields": "tract_geoid"}, 240, True),
    "lanes": ("https://services.sfmta.com/arcgis/rest/services/DataSF/master/MapServer/54",
              {"where": "1=1", "outFields": "CNN,LANES_AM,LANES_OP,LANES_PM", "returnGeometry": "false",
               "orderByFields": "OBJECTID"}, 15000, False),
    "bci": ("https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4",
            {"where": "1=1", "outFields": "cnn_sgmt_pkey,traffic_category_ft,traffic_category_tf",
             "returnGeometry": "false", "orderByFields": "cnn_sgmt_pkey"}, 15000, True),
}


class Source(object):
    """Rows of one input plus what is known of their vintage."""

    def __init__(self, name, rows, read_on, version, ref):
        self.name, self.rows, self.read_on, self.version, self.ref = name, rows, read_on, version, ref


# ---- DataSF -------------------------------------------------------------------------------------------------------

def _socrata(name, update):
    fxf, select, floor = SOCRATA[name]
    marker = MARKER_PREFIX + "socrata:" + fxf
    held = None
    try:
        held = sfdata.fetch(fxf, select=select, cache_dir=SOCRATA_CACHE, floor=floor, max_age_days=None,
                            refresh=False) if _held_socrata(fxf, select) else None
    except Exception:  # noqa: BLE001 - an unreadable cache entry is no cache entry
        held = None
    marks = _marks()
    if held is not None and not update:
        return Source(name, held.rows, held.fetched_on.isoformat(), (marks.get(fxf) or {}).get("version"), fxf)
    try:
        version = str(sfdata.metadata(fxf).get("rows_updated_ts"))
        # Unchanged only when DataSF's marker is the one recorded at the last read AND the held rows are the rows
        # that read wrote, so a held copy edited or cut short on disk is read again.
        if held is not None and marks.get(fxf) == {"version": version, "sha": _sha(held.rows)}:
            pipeline_state.record(marker, "unchanged", version=version, detail="%d rows held" % len(held.rows))
            return Source(name, held.rows, held.fetched_on.isoformat(), version, fxf)
        need = max(floor, int(len(held.rows) * REREAD_FLOOR)) if held is not None else floor
        got = sfdata.fetch(fxf, select=select, cache_dir=SOCRATA_CACHE, floor=need, refresh=True)
    except Exception as exc:  # noqa: BLE001
        if held is None:
            raise
        pipeline_state.record(marker, "failed", version=(marks.get(fxf) or {}).get("version"),
                              detail="re-read failed, held copy kept: %s" % exc)
        print("  %s (%s): re-read failed, keeping the held copy of %s: %s" % (name, fxf, held.fetched_on, exc),
              file=sys.stderr)
        return Source(name, held.rows, held.fetched_on.isoformat(), (marks.get(fxf) or {}).get("version"), fxf)
    status = "unchanged" if (held is not None and got.rows == held.rows) else "changed"
    if held is not None:
        diff = _diff_count(held.rows, got.rows)
        print("  %s (%s): re-read, %d rows, %d added or changed, %d gone" % ((name, fxf, len(got.rows)) + diff))
    marks[fxf] = {"version": version, "sha": _sha(got.rows)}
    _save_marks(marks)
    pipeline_state.record(marker, status, version=version, detail="%d rows" % len(got.rows))
    return Source(name, got.rows, got.fetched_on.isoformat(), version, fxf)


def _held_socrata(fxf, select):
    params = {"$select": select, "$order": ":id"}
    return os.path.exists(os.path.join(SOCRATA_CACHE, "%s.json" % sfdata._key(fxf, params)))


MARKS = os.path.join(SOCRATA_CACHE, "_markers.json")


def _marks():
    try:
        return json.load(open(MARKS, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_marks(marks):
    _write_cache(MARKS, marks)


def _sha(rows):
    import hashlib
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


def _diff_count(old, new):
    """(added or changed, gone) between two row lists, compared as whole rows."""
    a = collections.Counter(json.dumps(r, sort_keys=True) for r in old)
    b = collections.Counter(json.dumps(r, sort_keys=True) for r in new)
    return sum((b - a).values()), sum((a - b).values())


# ---- ArcGIS -------------------------------------------------------------------------------------------------------

def _get_json(url, params):
    raw = http_read(url + "?" + urllib.parse.urlencode(dict(params, f="json")), timeout=180)
    d = json.loads(raw)
    if "error" in d:
        raise RuntimeError("%s: %s" % (url, d["error"]))
    return d


def _arcgis_marker(url, params, has_edit_date):
    """The layer's own change marker: data edit date and row count, or the row count alone."""
    count = _get_json(url + "/query", {"where": params["where"], "returnCountOnly": "true"}).get("count")
    edit = None
    if has_edit_date:
        edit = ((_get_json(url, {}).get("editingInfo") or {}).get("dataLastEditDate"))
    return "%s|%s" % (edit, count), has_edit_date and edit is not None


def _arcgis_read(url, params, floor):
    feats, offset = [], 0
    page = 1000
    while True:
        d = _get_json(url + "/query", dict(params, resultOffset=offset, resultRecordCount=page))
        got = d.get("features") or []
        feats += got
        if not got or not d.get("exceededTransferLimit"):
            break
        offset += len(got)
    if len(feats) < floor:
        raise sfdata.TooFew("%s returned %d features, below the floor of %d" % (url, len(feats), floor))
    return feats


def _arcgis(name, update):
    url, params, floor, has_edit_date = ARCGIS[name]
    path = os.path.join(ARCGIS_CACHE, name + ".json")
    marker = MARKER_PREFIX + "arcgis:" + name
    held = None
    if os.path.exists(path):
        try:
            held = json.load(open(path, encoding="utf-8"))
        except ValueError:
            held = None
    if held is not None and not update:
        return Source(name, held["features"], held["read_on"], held["marker"], url)
    try:
        mark, settles = _arcgis_marker(url, params, has_edit_date)
        if held is not None and settles and held["marker"] == mark and held.get("sha") == _sha(held["features"]):
            pipeline_state.record(marker, "unchanged", version=mark, detail="%d features held" % len(held["features"]))
            return Source(name, held["features"], held["read_on"], mark, url)
        need = max(floor, int(len(held["features"]) * REREAD_FLOOR)) if held is not None else floor
        feats = _arcgis_read(url, params, need)
    except Exception as exc:  # noqa: BLE001
        if held is None:
            raise
        pipeline_state.record(marker, "failed", version=held["marker"], detail="re-read failed, held copy kept: %s" % exc)
        print("  %s: re-read failed, keeping the held copy of %s: %s" % (name, held["read_on"], exc), file=sys.stderr)
        return Source(name, held["features"], held["read_on"], held["marker"], url)
    if held is not None and held["features"] == feats:
        pipeline_state.record(marker, "unchanged" if settles else "checked", version=mark,
                              detail="%d features, re-read with no difference" % len(feats))
        if held["marker"] != mark or held.get("sha") != _sha(feats):
            held["marker"], held["sha"] = mark, _sha(feats)
            _write_cache(path, held)
        return Source(name, held["features"], held["read_on"], mark, url)
    import datetime as dt
    if held is not None:
        print("  %s: re-read, %d features, %d added or changed, %d gone" % ((name, len(feats)) + _diff_count(held["features"], feats)))
    blob = {"url": url, "params": params, "marker": mark, "read_on": dt.date.today().isoformat(), "features": feats,
            "sha": _sha(feats)}
    _write_cache(path, blob)
    pipeline_state.record(marker, "changed", version=mark, detail="%d features" % len(feats))
    return Source(name, feats, blob["read_on"], mark, url)


def _write_cache(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(blob, fh)
    os.replace(tmp, path)


# ---- all ----------------------------------------------------------------------------------------------------------

def load_all(update=False):
    """Every input as {name: Source}, in a fixed order."""
    import crash_tables  # ../, on the path below
    if update and not os.environ.get("CRASH_TABLES_HELD"):
        crash_tables.refresh(["crashes"], update=True)
    meta = crash_tables.info("crashes")
    out = {"crashes": Source("crashes", crash_tables.rows("crashes", columns=CRASH_COLUMNS), meta["read_on"],
                             meta["rowsUpdatedAt"], meta["id"])}
    for name in SOCRATA:
        out[name] = _socrata(name, update)
    for name in ARCGIS:
        out[name] = _arcgis(name, update)
    return out


def held(name):
    """One DataSF street source (a SOCRATA name) as a Source: the held copy the street lane last read and checked.

    Makes no request when the copy is held. For a reader such as analysis/crash-profiles/, which must use the same
    copy as the street columns rather than guess a cache file by name."""
    return _socrata(name, update=False)


def markers():
    """The pipeline-state keys this module records, for the orchestrator's set_step()."""
    return sorted([MARKER_PREFIX + "socrata:" + v[0] for v in SOCRATA.values()]
                  + [MARKER_PREFIX + "arcgis:" + k for k in ARCGIS])
