"""Settings that name private infrastructure (a cloud project, a bucket, a review board), kept out of the repo.

    from lib import settings
    settings.get("GCP_PROJECT")              # None when unset
    settings.get("RT_ARCHIVE_BUCKET", "x")   # a default when unset

Each key is read from the environment first, then from local-settings.json at the repo root, which is
gitignored (local-settings.example.json lists the keys). Every key is optional: code that reads one does
without it, skipping only the step that needs it, so a fresh clone runs with neither file nor variables.

Keys:
  GCP_PROJECT          Google Cloud project that holds the Muni realtime archive bucket.
  RT_ARCHIVE_BUCKET    The bucket's name, without gs://.
  BOARD_DOCS           A JSON object of repo path -> review-board doc id, for generated files someone reviews
                       on a board. The pipeline prints which of them changed.
  SFBIKE_CHECK_DOC     The review-board doc id for out/sfbike-check/check.md.
  ALERT_REPO           The GitHub repo the scheduled jobs open data-refresh issues on (owner/name).
"""

import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE = os.path.join(_ROOT, "local-settings.json")
_cache = None


def _file():
    global _cache
    if _cache is None:
        try:
            with open(_FILE) as f:
                _cache = json.load(f)
        except (FileNotFoundError, ValueError):
            _cache = {}
    return _cache


def get(key, default=None):
    """The setting's value from the environment or local-settings.json; `default` when neither has it."""
    v = os.environ.get(key)
    if v not in (None, ""):
        return v
    v = _file().get(key)
    return default if v in (None, "") else v


def get_json(key, default=None):
    """A setting that holds JSON (an object or list), parsed; `default` when unset or unreadable."""
    v = get(key)
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except ValueError:
        return default
