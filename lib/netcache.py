"""On-disk cache of the built walk network (walknet.Graph plus every census block's join to it), so the school and access models load it in about a second instead of rebuilding it.

    from lib import netcache
    G = netcache.graph()                 # walknet's graph, from .cache/walknet/ when current
    G = netcache.graph(use_cache=False)  # rebuild from the source files (--no-cache)

Bryan, 2026-10-01:
"Yes cache". Building the network parses data/osm-cache/sf-walk.json, finds
its connected pieces, grids its edges and joins each of the 5,986 census
blocks along its frontage, all in Python on one core.

WHAT IS CACHED. The graph's arrays (node coordinates, edges, lengths, highway
tags, which edges a point may join, the 50 m grid) and walknet's snap for
every 2020 census block interior point (data/extract/census-blocks/2020.json),
as one numpy .npz with no pickled objects. The edges each bikeway line rides
(school-travel-time.edges_of) are cached beside it by edges(), keyed by the
lines themselves.

THE KEY is a sha256 over FORMAT, walknet.py's source, this file's source,
every input file's bytes (the OSM extract and the census block points and
outlines for 2010 and 2020, which walknet.use_census_outlines() reads), the
walknet parameters, and how many outlines are registered. Any change to any of
them gives a new file name, so a stale cache is never read; old files are
deleted when a new one is written. A file that fails to read for any reason is
rebuilt. Writes go to a temporary file in the same directory and are renamed
into place, so a crash never leaves a half-written cache.

A loaded graph is the same as a built one, value for value: floats round-trip
float64 exactly and every list keeps its order (checked by scripts/
school-travel-time.py --no-cache against a cached run, byte for byte).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import hashlib
import inspect
import json
import os
import sys
import tempfile

import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import walknet  # noqa: E402

FORMAT = 2
DIR = os.path.join(ROOT, ".cache", "walknet")
BLOCKS = os.path.join(ROOT, "data", "extract", "census-blocks")
NONE_TAG = "\x00"  # an edge with no highway tag
STATS = {}  # what the last graph() call did, for the scripts' log lines


def _sha_file(h, path):
    h.update(path.encode())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)


def _inputs():
    out = [walknet.CACHE, os.path.abspath(walknet.__file__), os.path.abspath(__file__)]
    for v in ("2010", "2020"):
        out += [os.path.join(BLOCKS, "%s.json" % v), os.path.join(BLOCKS, "outlines-%s.json" % v)]
    return out


def graph_key():
    h = hashlib.sha256()
    h.update(("format %d\n" % FORMAT).encode())
    for p in _inputs():
        _sha_file(h, p)
    params = {k: getattr(walknet, k) for k in ("EARTH", "LAT0", "SAMPLE_M", "SOURCE_SNAP_M", "FALLBACK_SNAP_M",
                                               "TARGET_SLACK_M", "MIN_COMPONENT", "FRONTAGE_SNAP_M", "CELL_M")}
    params["outlines"] = len(walknet.OUTLINES)
    h.update(json.dumps(params, sort_keys=True).encode())
    return h.hexdigest()[:20]


def _write_npz(path, arrays):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".npz")
    try:
        with os.fdopen(fd, "wb") as f:
            numpy.savez(f, **arrays)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _prune(prefix, keep):
    for name in os.listdir(DIR):
        if name.startswith(prefix) and name.endswith(".npz") and name != keep:
            try:
                os.remove(os.path.join(DIR, name))
            except OSError:
                pass


def _block_points():
    rows = json.load(open(os.path.join(BLOCKS, "2020.json")))["records"]
    return sorted({(r["lon"], r["lat"]) for r in rows})


def _save_graph(G, path, points):
    cell_keys = list(G.cells.keys())
    cell_len = [len(G.cells[k]) for k in cell_keys]
    snaps = [G.snap(lon, lat) for lon, lat in points]
    tags = sorted({NONE_TAG if t is None else t for t in G.ehw})
    code = {(None if t == NONE_TAG else t): i for i, t in enumerate(tags)}
    flat = [s for sn in snaps for s in sn]
    _write_npz(path, {
        "x": numpy.array(G.x, dtype=numpy.float64), "y": numpy.array(G.y, dtype=numpy.float64),
        "eu": numpy.array(G.eu, dtype=numpy.int64), "ev": numpy.array(G.ev, dtype=numpy.int64),
        "elen": numpy.array(G.elen, dtype=numpy.float64),
        "ehw_tags": numpy.array(tags, dtype=str),
        "ehw": numpy.array([code[t] for t in G.ehw], dtype=numpy.int32),
        "joinable": numpy.array(G.joinable, dtype=bool),
        "component_sizes": numpy.array(G.component_sizes, dtype=numpy.int64),
        "meta": numpy.array(json.dumps({"osm_base": G.osm_base, "ways": G.ways, "missing_nodes": G.missing_nodes})),
        "cell_x": numpy.array([k[0] for k in cell_keys], dtype=numpy.int64),
        "cell_y": numpy.array([k[1] for k in cell_keys], dtype=numpy.int64),
        "cell_len": numpy.array(cell_len, dtype=numpy.int64),
        "cell_edges": numpy.array([e for k in cell_keys for e in G.cells[k]], dtype=numpy.int64),
        "snap_lon": numpy.array([p[0] for p in points], dtype=numpy.float64),
        "snap_lat": numpy.array([p[1] for p in points], dtype=numpy.float64),
        "snap_len": numpy.array([len(sn) for sn in snaps], dtype=numpy.int64),
        "snap_e": numpy.array([s[0] for s in flat], dtype=numpy.int64),
        "snap_t": numpy.array([s[1] for s in flat], dtype=numpy.float64),
        "snap_d": numpy.array([s[2] for s in flat], dtype=numpy.float64),
    })


def _split(flat, lens):
    out, i = [], 0
    for n in lens:
        out.append(flat[i:i + n])
        i += n
    return out


def _load_graph(path):
    z = numpy.load(path, allow_pickle=False)
    G = walknet.Graph.__new__(walknet.Graph)
    meta = json.loads(str(z["meta"]))
    G.osm_base, G.ways, G.missing_nodes = meta["osm_base"], meta["ways"], meta["missing_nodes"]
    G.x, G.y = z["x"].tolist(), z["y"].tolist()
    G.eu, G.ev, G.elen = z["eu"].tolist(), z["ev"].tolist(), z["elen"].tolist()
    tags = [None if t == NONE_TAG else t for t in z["ehw_tags"].tolist()]
    G.ehw = [tags[i] for i in z["ehw"].tolist()]
    G.joinable = z["joinable"].tolist()
    G.component_sizes = z["component_sizes"].tolist()
    # walknet.Graph builds adj edge by edge, u's entry then v's: the same order here.
    adj = [[] for _ in range(len(G.x))]
    for u, v, L in zip(G.eu, G.ev, G.elen):
        adj[u].append((v, L))
        adj[v].append((u, L))
    G.adj = adj
    G.cells = collections.defaultdict(list)
    for cx, cy, es in zip(z["cell_x"].tolist(), z["cell_y"].tolist(),
                          _split(z["cell_edges"].tolist(), z["cell_len"].tolist())):
        G.cells[(cx, cy)] = es
    G._snap = {}
    flat = list(zip(z["snap_e"].tolist(), z["snap_t"].tolist(), z["snap_d"].tolist()))
    for lon, lat, sn in zip(z["snap_lon"].tolist(), z["snap_lat"].tolist(), _split(flat, z["snap_len"].tolist())):
        G._snap[(lon, lat)] = sn
    if len(G.eu) != len(G.elen) or len(G.joinable) != len(G.eu) or len(G._snap) != len(z["snap_len"]):
        raise ValueError("inconsistent cache arrays")
    return G


def graph(use_cache=True):
    """walknet's graph with every 2020 census block's snap, from the cache when it is current; sets walknet's shared graph."""
    if walknet._GRAPH is not None and getattr(walknet._GRAPH, "_from_netcache", None) == use_cache:
        return walknet._GRAPH
    if not use_cache:
        STATS.update(source="built (--no-cache)")
        G = walknet.Graph()
    else:
        key = graph_key()
        name = "graph-%s.npz" % key
        path = os.path.join(DIR, name)
        G = None
        if os.path.exists(path):
            try:
                G = _load_graph(path)
                STATS.update(source="cache " + os.path.relpath(path, ROOT))
            except Exception as err:  # noqa: BLE001 - any bad read means rebuild
                print("  network cache unreadable (%s: %s); rebuilding" % (type(err).__name__, err))
                G = None
        if G is None:
            G = walknet.Graph()
            _save_graph(G, path, _block_points())
            _prune("graph-", name)
            STATS.update(source="built, cached to " + os.path.relpath(path, ROOT))
    G._from_netcache = use_cache
    walknet._GRAPH = G
    return G


def edges(fn, net, lines, key_parts, use_cache=True):
    """fn(net, lines), the edges each line rides, cached under the graph key, the lines and key_parts (source and parameters)."""
    if not use_cache:
        return fn(net, lines)
    h = hashlib.sha256()
    h.update(("format %d %s\n" % (FORMAT, graph_key())).encode())
    h.update(json.dumps(key_parts, sort_keys=True, default=str).encode())
    h.update(json.dumps(lines).encode())
    name = "edges-%s.npz" % h.hexdigest()[:20]
    path = os.path.join(DIR, name)
    if os.path.exists(path):
        try:
            z = numpy.load(path, allow_pickle=False)
            keys = z["keys"].tolist()
            out = collections.defaultdict(set)
            for k, es in zip(keys, _split(z["edges"].tolist(), z["lens"].tolist())):
                out[k] = set(es)
            return out, set(z["weak"].tolist())
        except Exception as err:  # noqa: BLE001
            print("  edge cache unreadable (%s: %s); rebuilding" % (type(err).__name__, err))
    out, weak = fn(net, lines)
    keys = list(out.keys())
    _write_npz(path, {"keys": numpy.array(keys, dtype=str),
                      "lens": numpy.array([len(out[k]) for k in keys], dtype=numpy.int64),
                      "edges": numpy.array([e for k in keys for e in sorted(out[k])], dtype=numpy.int64),
                      "weak": numpy.array(sorted(weak), dtype=str)})
    _prune("edges-", name)
    return out, weak


def source_of(*objs):
    """The source text of functions, for a cache key (a class from a module loaded by path has no findable source)."""
    return [inspect.getsource(o) for o in objs]
