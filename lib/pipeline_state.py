"""When each source was last checked, and what the check found.

data/pipeline-state/sources.json is gitignored: it changes on every run, and a
tracked file that changes on every run is exactly what an idempotent pipeline
must not have. The audit's freshness check (F3) reads it when present.

    from lib import pipeline_state
    pipeline_state.record("socrata:3psu-pn9h", status="unchanged", version="2026-09-20")
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import json
import os

ROOT = paths.ROOT
# PIPELINE_STATE_DIR moves it, so a test can run a step without touching the real record.
PATH = os.path.join(os.environ.get("PIPELINE_STATE_DIR") or os.path.join(ROOT, "data", "pipeline-state"),
                    "sources.json")


def load():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def record(source, status, version=None, detail=None, last_good=None):
    """status: unchanged, changed, checked (a bounded re-read that reached everything), failed, skipped, stale (current with the source, whose own data has run out), or kept (checked, with changed items left on their last answer by design, e.g. a model reader with no API key on this host). version: the source's own last-change marker.

    A failed check keeps the time of the last check that succeeded as
    `last_good`, so the freshness check (F3) ages the source from it. The `last_good` argument stands in only when the
    source has no check of its own to carry over (its first failure)."""
    state = load()
    prev = state.get(source) or {}
    own = prev.get("checked") if prev.get("status") not in (None, "failed", "skipped") else prev.get("last_good")
    last_good = own or last_good
    state[source] = {"checked": dt.datetime.now().isoformat(timespec="seconds"), "status": status,
                     "version": version, "detail": detail}
    if status in ("failed", "skipped") and last_good:
        state[source]["last_good"] = last_good
    if prev.get("step"):
        state[source]["step"] = prev["step"]
    _save(state)


def set_step(sources, step):
    """Name the pipeline step that records these sources, so the freshness check ages each one on its step's update
    interval (a weekly step's marker is not late after one day). pipeline/transportation-update.py calls this after
    each step with the entries the step wrote; record() carries the name over to later checks."""
    state = load()
    moved = [k for k in sources if k in state and state[k].get("step") != step]
    for k in moved:
        state[k]["step"] = step
    if moved:
        _save(state)


def refreshed(source, failures, version=None, detail=None):
    """Record the outcome of a bounded re-read (a source with no change marker
    of its own, whose script re-reads a named window each run).

    `failures` lists every item the re-read could not reach, whether it kept
    the held copy or had none. Any failure records the source as failed, so
    the orchestrator names it, the extract ages from its last good check, and
    the freshness check (F3) can expire it; none records it as checked."""
    failures = sorted(str(f) for f in failures or [])
    if failures:
        record(source, "failed", version=version,
               detail="%d not reached, held copy kept: %s" % (len(failures), "; ".join(failures[:5])))
    else:
        record(source, "checked", version=version, detail=detail)


def _save(state):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, PATH)
