"""Find the repo root and any script in it by file name, so a script works wherever its folder sits.

A script reaches this module with three lines at its top, which find the root as the nearest folder above the
script that holds lib/paths.py:

    import pathlib, sys  # noqa: E401
    sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
    from lib import paths  # noqa: E402

Then:

    paths.ROOT                        the repo root, a str
    paths.LIB                         lib/, a str
    paths.script("school-sim.py")     the path of a script, found by exact file name under pipeline/, tools/ and lib/
    paths.load("school-sim.py")       that script imported as a module (hyphens become underscores in its name)

File names are unique across those folders, so a name is enough; script() raises when a name matches no file or
more than one. Importing this module also puts the root at the front of sys.path and lib/ at its end, so
`from lib import stable` and the older `import sfdata` both resolve.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib")
SEARCH = ("pipeline", "tools", "lib")
SKIP = {"__pycache__", "node_modules", ".git"}

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if LIB not in sys.path:
    sys.path.append(LIB)

_index = None


def _build():
    found = {}
    for top in SEARCH:
        for d, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = sorted(x for x in dirs if x not in SKIP)
            for f in files:
                found.setdefault(f, []).append(os.path.join(d, f))
    return found


def script(name):
    """The absolute path of the file called `name` (with its extension) under pipeline/, tools/ or lib/."""
    global _index
    if _index is None:
        _index = _build()
    hits = _index.get(name) or []
    if len(hits) != 1:
        _index = _build()  # a file added since the first call
        hits = _index.get(name) or []
    if not hits:
        raise FileNotFoundError("paths.script: no file named %r under %s" % (name, ", ".join(SEARCH)))
    if len(hits) > 1:
        raise LookupError("paths.script: %r names more than one file: %s" % (name, ", ".join(hits)))
    return hits[0]


def load(name, module=None, register=False):
    """Import the script called `name` and return the module. A name without an extension gets .py.

    `module` is the module's __name__, by default the file's stem with hyphens as underscores. Each call
    runs the file afresh, as importlib's spec_from_file_location does. With register=True the module is
    put in sys.modules under that name before it runs, which dataclasses and pickle need.
    """
    if not os.path.splitext(name)[1]:
        name += ".py"
    path = script(name)
    module = module or os.path.splitext(name)[0].replace("-", "_")
    spec = importlib.util.spec_from_file_location(module, path)
    mod = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[module] = mod
    spec.loader.exec_module(mod)
    return mod
