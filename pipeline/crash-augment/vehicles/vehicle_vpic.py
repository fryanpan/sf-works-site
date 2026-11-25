"""Read NHTSA's vPIC API (makes, model names, Canadian curb weights) through an on-disk cache, so a rerun makes no network call.

    import vehicle_vpic as vpic
    vpic.makes()                         # {"TOYOTA": {"car", "truck", ...}, ...} from GetMakesForVehicleType
    vpic.models("TOYOTA")                # {"Camry", "RAV4", ...} from GetModelsForMake, every model year at once
    vpic.canadian_specs("TOYOTA", 2020)  # [("CAMRY 4DR SEDAN LE", 3296.1), ...] from GetCanadianVehicleSpecifications

Endpoints, all under https://vpic.nhtsa.dot.gov/api/vehicles/ with format=json:

  GetMakesForVehicleType/<type>                every make NHTSA lists for one vehicle type.
  GetModelsForMake/<m>                         every model name a make has registered, all model years.
                                               (GetModelsForMakeYear gives the same names one year at a
                                               time; matching a name does not need its year, so one
                                               request per make is enough.)
  GetCanadianVehicleSpecifications/?Year=<y>&Make=<m>&units=US
                                               Transport Canada's dimensions for every trim of a
                                               make in one model year; `CW` is curb weight in lb.

Every answer is kept under .cache/crash-augment/vpic/ (gitignored), one JSON file per request,
named by a hash of its URL. A cached answer is never asked again: vPIC's answers for past model
years do not change, and a new model year is a new request. With VPIC_OFFLINE=1 in the
environment, or after `set_offline()`, an uncached request raises instead of reaching the
network, which is how a rerun proves it made no network call.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request

BASE = "https://vpic.nhtsa.dot.gov/api/vehicles/"
CACHE = os.environ.get("VPIC_CACHE_DIR") or os.path.join(paths.ROOT, ".cache", "crash-augment", "vpic")
# The vehicle types whose makes count as motor vehicle makes. Trailers and incomplete vehicles are left out:
# their makers' names ("BIG TEX", "UTILITY") collide with words officers write.
VEHICLE_TYPES = ("car", "truck", "multipurpose passenger vehicle (mpv)", "bus", "motorcycle",
                 "low speed vehicle (lsv)")
_offline = os.environ.get("VPIC_OFFLINE") == "1"
_lock = threading.Lock()
# vPIC's firewall answers 403 to a client that asks too fast, so network requests are spaced at least this
# far apart across all threads, and a 403 or 429 waits a minute or more before the next try.
MIN_INTERVAL_S = 0.6
_last = [0.0]
STATS = {"cached": 0, "fetched": 0}


class Offline(RuntimeError):
    """An uncached vPIC request was made while the network was turned off."""


def set_offline(flag=True):
    global _offline
    _offline = flag


def _path(url):
    return os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest()[:20] + ".json")


def get(path, params=None):
    """The Results list of one vPIC request, from the cache when it is there."""
    q = dict(params or {})
    q["format"] = "json"
    url = BASE + path + "?" + urllib.parse.urlencode(sorted(q.items()))
    p = _path(url)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            STATS["cached"] += 1
            return json.load(fh)["results"]
    if _offline:
        raise Offline("vPIC request not in the cache and the network is off: " + url)
    last = None
    for attempt in range(6):
        with _lock:
            wait = _last[0] + MIN_INTERVAL_S - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "sf-works-pipeline"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
            break
        except Exception as exc:  # noqa: BLE001 - vPIC times out now and then; retry, then raise
            last = exc
            blocked = getattr(exc, "code", None) in (403, 429)
            time.sleep((60 * (attempt + 1)) if blocked else 2 * (attempt + 1))
    else:
        raise RuntimeError("vPIC request failed six times: %s (%s)" % (url, last))
    results = body.get("Results") or []
    os.makedirs(CACHE, exist_ok=True)
    tmp = p + ".%d.tmp" % threading.get_ident()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"url": url, "results": results}, fh, sort_keys=True)
    os.replace(tmp, p)
    with _lock:
        STATS["fetched"] += 1
    return results


def makes():
    """{MAKE NAME: set of vehicle types} over VEHICLE_TYPES, names upper-cased as vPIC gives them."""
    out = {}
    for t in VEHICLE_TYPES:
        for r in get("GetMakesForVehicleType/" + urllib.parse.quote(t)):
            name = (r.get("MakeName") or "").strip().upper()
            if name:
                out.setdefault(name, set()).add(t)
    return out


def models(make):
    """The set of model names vPIC lists for `make`, over every model year."""
    out = set()
    for r in get("GetModelsForMake/" + urllib.parse.quote(make)):
        name = (r.get("Model_Name") or "").strip()
        if name:
            out.add(name)
    return out


def canadian_specs(make, year):
    """[(trim name, curb weight lb)] for every trim of `make` in model year `year` that has a weight."""
    out = []
    for r in get("GetCanadianVehicleSpecifications/", {"Year": year, "Make": make, "units": "US"}):
        spec = {s.get("Name"): s.get("Value") for s in r.get("Specs") or []}
        try:
            cw = float(spec.get("CW") or "")
        except ValueError:
            continue
        if cw > 0 and spec.get("Model"):
            out.append((spec["Model"].strip(), cw))
    return sorted(out)
