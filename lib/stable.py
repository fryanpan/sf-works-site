"""Write a file only when what it says has changed, so a rerun with no new data leaves git clean.

Bryan, 2026-09-28: the transportation pipeline "should be idempotent if no new
data shows up". Two things broke that on a plain rerun from cache:

  * Date stamps. Nearly every output carries "generated": today, a
    "queried 2026-09-28" tag or a fetched_on date, so a rerun on a new day
    rewrites the file even though every figure is the same.
  * Set ordering. Python randomises string hashes per process, so a list
    built from a set, or a sort with ties, comes out in a different order
    each run. pipeline/transportation-update.py pins PYTHONHASHSEED to fix
    that; this module handles the stamps.

`same(old, new)` compares two texts with their stamps masked. `keep_if_same`
puts a file's previous bytes back when the only difference is a stamp, and
`write_text` / `write_json` never write in that case. A stamp therefore
records when the content last changed, not when a script last ran. When a
source was last CHECKED is recorded separately, in data/pipeline-state/,
which is gitignored because it changes on every run.
"""

import json
import os
import re

# A JSON key whose value is a date or timestamp of the run, not of the data.
STAMP_KEYS = ("generated", "generated_on", "generatedAt", "queried", "fetched", "fetched_on",
              "fetchedOn", "checked", "checked_on", "asOf", "built", "builtOn", "run", "runOn", "today")
_DATE = r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?"
_KEY_RE = re.compile(r'("(?:%s)"\s*:\s*)"%s"' % ("|".join(STAMP_KEYS), _DATE))
# A provenance phrase in prose or in a string value: "queried 2026-09-28",
# "read 2026-09-28", "generated 2026-09-28". "As of" is left alone: it often
# carries the data's own date (a layer's last edit), which is content.
_PHRASE_RE = re.compile(r"\b(queried|read|generated|fetched|checked|built|Generated|Read|Queried|Built)"
                        r"(\s+(?:on\s+)?)%s" % _DATE)


def mask(text):
    """The text with every run stamp replaced by a placeholder."""
    text = _KEY_RE.sub(r'\1"<stamp>"', text)
    return _PHRASE_RE.sub(r"\1\2<stamp>", text)


def same(old, new):
    """True when two texts differ at most in their run stamps."""
    return old == new or mask(old) == mask(new)


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return None


def write_text(path, text):
    """Write `text` unless the file already says the same thing. Returns True on a write."""
    old = read_text(path)
    if old is not None and same(old, text):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    path = os.fspath(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def write_json(path, obj, end="\n", **dump):
    """json.dump to `path` with the stamp rule. `dump` is passed to json.dumps.

    `end` follows the JSON text; a script moved here from a bare json.dump
    passes end="" (and ensure_ascii=True where it relied on the default), so
    its file keeps the bytes it had."""
    dump.setdefault("ensure_ascii", False)
    return write_text(path, json.dumps(obj, **dump) + end)


def keep_if_same(path, old_bytes):
    """Put `old_bytes` back at `path` when the new file differs only in stamps.

    Returns "restored", "changed", "new" or "unchanged". Used by the
    orchestrator around scripts that write with plain open().
    """
    if old_bytes is None:
        return "new" if os.path.exists(path) else "unchanged"
    try:
        with open(path, "rb") as fh:
            new_bytes = fh.read()
    except FileNotFoundError:
        return "changed"
    if new_bytes == old_bytes:
        return "unchanged"
    try:
        if same(old_bytes.decode("utf-8"), new_bytes.decode("utf-8")):
            with open(path, "wb") as fh:
                fh.write(old_bytes)
            return "restored"
    except UnicodeDecodeError:
        pass
    return "changed"


def _selftest():
    a = '{\n "generated": "2026-09-24",\n "n": 3,\n "tag": "[DataSF x — queried 2026-09-21]"\n}\n'
    b = '{\n "generated": "2026-09-28",\n "n": 3,\n "tag": "[DataSF x — queried 2026-09-28]"\n}\n'
    c = b.replace('"n": 3', '"n": 4')
    assert same(a, b) and not same(a, c)
    assert same("Read 2026-09-01. 12 rows.", "Read 2026-09-28. 12 rows.")
    assert not same("Built in 2024-05-01.", "Built in 2024-06-01.")
    print("stable.py selftest ok")


if __name__ == "__main__":
    _selftest()
