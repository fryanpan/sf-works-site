"""Polite HTTP for the meeting mirrors: one pause per request, a real backoff, and an optional byte cache.

Every deciding body's fetch script reaches the network through a Fetcher, so
the rules live in one place:

  - a pause between requests (sfmta.com answers a fast walk with 403, not 429,
    and three quick retries burned through in six seconds the first time);
  - a backoff long enough for a throttle to lift (5, 20, 60 seconds);
  - raw bytes cached under .cache/<name>/ keyed by URL, when the caller says
    the document is final. The cache is gitignored: raw pages and PDFs carry
    staff contacts, and only the scrubbed mirror under data/ is tracked.

    from lib.fetch import Fetcher, pdf_text
    f = Fetcher("sfcta-board")
    html = f.get(url)                    # cached
    html = f.get(url, cache=False)       # always the network (a listing, a draft)
    text = pdf_text(f.get(pdf_url, binary=True))

A source script with no Fetcher reads through read(), which retries a transient failure (HTTP 5xx or 429, a timeout,
a dropped connection) with the same backoff, and hands the error it finally gives up on to upstream_failed():

    from lib.fetch import read, upstream_failed
    try:
        raw = read(URL)
    except Exception as e:
        upstream_failed("transtat:muni-ridership", e, step="muni-ridership")

A transient failure there records the source's marker as failed in data/pipeline-state/sources.json (so
pipeline/refresh-freshness.py ages it from its last good check), prints a STALE warning, and exits 0: the last good
file stays and pipeline/transportation-update.py runs the builds on it, naming the source under REFRESH FAILED.
Any other error (a 404, a page that no longer parses) exits 2, which stops the run like a failed check.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import hashlib
import http.client
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = paths.ROOT
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
BACKOFF = (5, 20, 60)
RETRY_CODES = (403, 429, 500, 502, 503, 504)


TRANSIENT_CODES = (429, 500, 502, 503, 504)


def is_transient(exc):
    """True for an upstream failure that a later run can expect to clear by itself: HTTP 429 or any 5xx, a timeout,
    a refused or dropped connection, a body cut short. False for everything else, a 404 or a parse error among them."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in TRANSIENT_CODES or exc.code >= 500
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException))


def read(url, headers=None, timeout=120, tries=4, backoff=BACKOFF):
    """The body of `url` as bytes. A transient failure (is_transient) is retried after 5, 20 and 60 seconds; the
    last one is raised, as is any other error at once."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return fh.read()
        except Exception as exc:  # noqa: BLE001
            if not is_transient(exc) or i == tries - 1:
                raise
            wait = backoff[min(i, len(backoff) - 1)]
            print("  %s: %s; retrying in %ds" % (url.split("?")[0], exc, wait), file=sys.stderr)
            time.sleep(wait)


def upstream_failed(marker, exc, step=None):
    """A source script's read gave up: keep the last good file and end the script.

    Transient (is_transient): record `marker` failed in sources.json, with the last good check carried over (from the
    marker's own last success, or else from step:<step>, the orchestrator's record of the step), print a STALE warning
    and exit 0, so the builds run on the last good copy. Anything else: exit 2, which stops the run."""
    from lib import pipeline_state
    if not is_transient(exc):
        print("read failed, keeping the last good file: %s" % exc, file=sys.stderr)
        sys.exit(2)
    state = pipeline_state.load()
    fallback = None
    st = state.get("step:" + step) if step else None
    if st:
        fallback = st.get("last_good") if st.get("status") in ("failed", "skipped") else st.get("checked")
    pipeline_state.record(marker, "failed", last_good=fallback,
                          detail="stale: upstream did not answer (%s); last good file kept" % exc)
    print("STALE: %s did not answer (%s) after retries; keeping the last good file, and the builds run on it"
          % (marker, exc))
    sys.exit(0)


class Fetcher(object):
    def __init__(self, name, pause=0.7, refetch=False, headers=None):
        self.name = name
        self.pause = pause
        self.refetch = refetch
        self.cache_dir = os.path.join(ROOT, ".cache", name)
        self.headers = {"User-Agent": UA,
                        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
                        "Accept-Language": "en-US,en;q=0.9"}
        self.headers.update(headers or {})
        self.requests = 0

    def _path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())

    def cached(self, url):
        return os.path.exists(self._path(url))

    def get(self, url, binary=False, cache=True, tries=4):
        """The body of `url`, from the byte cache when allowed, else the network.

        Raises the last error when every try fails; the caller records that
        meeting as unreachable rather than as a meeting with nothing in it.
        """
        path = self._path(url)
        if cache and not self.refetch and os.path.exists(path):
            raw = open(path, "rb").read()
            return raw if binary else raw.decode("utf-8", "replace")
        req = urllib.request.Request(url, headers=self.headers)
        for i in range(tries):
            try:
                time.sleep(self.pause)
                self.requests += 1
                with urllib.request.urlopen(req, timeout=120) as fh:
                    raw = fh.read()
                if cache:
                    os.makedirs(self.cache_dir, exist_ok=True)
                    with open(path, "wb") as out:
                        out.write(raw)
                return raw if binary else raw.decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_CODES and i < tries - 1:
                    time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if i == tries - 1:
                    raise
                time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])


def pdf_text(raw):
    """A PDF's text via pdftotext -layout, or None when it is not a readable PDF."""
    if not raw or not raw.lstrip()[:5].startswith(b"%PDF"):
        return None
    try:
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=raw,
                           capture_output=True, timeout=240)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None
