"""Record which repo files a Python script reads and writes, for the pipeline.

pipeline/transportation-update.py puts this directory on PYTHONPATH when it runs
a build step, so Python loads it at start-up. At exit it appends one JSON line
to $TRACE_LOG: the files opened for reading, the files written, the
directories listed (a glob that would find a new file), and the repo modules
imported. The next run hashes exactly those, so a step is skipped only when
nothing it actually read has changed. Nothing here changes what a script does.
"""

import atexit
import builtins
import io
import json
import os
import pathlib
import sys

_LOG = os.environ.get("TRACE_LOG")
_ROOT = os.path.realpath(os.environ.get("TRACE_ROOT", os.getcwd()))
_seen = {"r": set(), "w": set(), "d": set()}
_open = builtins.open


def _rel(f):
    try:
        p = os.path.realpath(os.fspath(f))
    except Exception:  # noqa: BLE001
        return None
    if not p.startswith(_ROOT + os.sep) or "/.git/" in p or "__pycache__" in p:
        return None
    return os.path.relpath(p, _ROOT)


def _rec(f, mode):
    r = _rel(f)
    if r:
        _seen["w" if any(c in mode for c in "wax+") else "r"].add(r)


def _traced_open(f, mode="r", *a, **k):
    if isinstance(f, (str, bytes, os.PathLike)):
        _rec(f, mode)
    return _open(f, mode, *a, **k)


builtins.open = _traced_open
io.open = _traced_open

_pr, _pw = pathlib.Path.read_text, pathlib.Path.write_text
_prb, _pwb = pathlib.Path.read_bytes, pathlib.Path.write_bytes
pathlib.Path.read_text = lambda s, *a, **k: (_rec(s, "r"), _pr(s, *a, **k))[1]
pathlib.Path.read_bytes = lambda s, *a, **k: (_rec(s, "r"), _prb(s, *a, **k))[1]
pathlib.Path.write_text = lambda s, *a, **k: (_rec(s, "w"), _pw(s, *a, **k))[1]
pathlib.Path.write_bytes = lambda s, *a, **k: (_rec(s, "w"), _pwb(s, *a, **k))[1]

_replace = os.replace


def _traced_replace(a, b, *x, **k):
    _rec(b, "w")
    return _replace(a, b, *x, **k)


os.replace = _traced_replace

_listdir, _scandir = os.listdir, os.scandir


def _dir(p):
    r = _rel(p if p is not None else ".")
    if r:
        _seen["d"].add(r)


def _traced_listdir(p=None):
    _dir(p)
    return _listdir(p) if p is not None else _listdir()


def _traced_scandir(p=None):
    _dir(p)
    return _scandir(p) if p is not None else _scandir()


os.listdir = _traced_listdir
os.scandir = _traced_scandir


# Network. With $NET_LOG set (the orchestrator sets it for source steps), every
# HTTP request the script makes through http.client (urllib and anything built
# on it) is appended to $NET_LOG at exit, one JSON line each: method, URL,
# status and the bytes of body read. This is how a run shows, per source, that
# it asked only its change markers when nothing moved.
_NET = os.environ.get("NET_LOG")
_net_recs = []
if _NET:
    import http.client as _hc

    # putrequest, not request: urllib calls request(), which calls putrequest();
    # urllib3 (requests) overrides request() and calls putrequest() itself.
    _hput, _hresp = _hc.HTTPConnection.putrequest, _hc.HTTPConnection.getresponse
    # _safe_read too: urllib3 reads a chunked body through it directly.
    _reads = {k: getattr(_hc.HTTPResponse, k) for k in ("read", "read1", "readinto", "readline", "_safe_read")}

    def _net_putrequest(self, method, url, *a, **k):
        https = isinstance(self, _hc.HTTPSConnection) or getattr(self, "default_port", 80) == 443
        scheme = "https" if https else "http"
        self._net_url = url if "://" in url else "%s://%s%s" % (scheme, self.host, url)
        self._net_method = method
        return _hput(self, method, url, *a, **k)

    def _net_getresponse(self, *a, **k):
        r = _hresp(self, *a, **k)
        r._net = {"m": getattr(self, "_net_method", "?"), "u": getattr(self, "_net_url", "?"),
                  "s": r.status, "b": 0}
        _net_recs.append(r._net)
        return r

    def _counting(name):
        orig = _reads[name]

        def wrapped(self, *a, **k):
            # Only the outermost read counts: read() may call readinto().
            if getattr(self, "_net_in", False):
                return orig(self, *a, **k)
            self._net_in = True
            try:
                out = orig(self, *a, **k)
            finally:
                self._net_in = False
            rec = getattr(self, "_net", None)
            if rec is not None and out:
                rec["b"] += out if isinstance(out, int) else len(out)
            return out
        return wrapped

    _hc.HTTPConnection.putrequest = _net_putrequest
    _hc.HTTPConnection.getresponse = _net_getresponse
    for _k in _reads:
        setattr(_hc.HTTPResponse, _k, _counting(_k))

    @atexit.register
    def _net_dump():
        with _open(_NET, "a") as fh:
            for rec in _net_recs:
                fh.write(json.dumps(rec) + "\n")


@atexit.register
def _dump():
    if not _LOG:
        return
    mods = set()
    for m in list(sys.modules.values()):
        r = _rel(getattr(m, "__file__", None) or "")
        if r and r.endswith(".py"):
            mods.add(r)
    with _open(_LOG, "a") as fh:
        fh.write(json.dumps({"argv": sys.argv, "r": sorted(_seen["r"] - _seen["w"]),
                             "w": sorted(_seen["w"]), "d": sorted(_seen["d"]),
                             "m": sorted(mods)}) + "\n")
