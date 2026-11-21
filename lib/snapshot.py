"""Copy the files a pipeline step may write before it runs, so a failed step can be put back exactly.

    snap = Snapshot(ROOT, ["data/extract/sfmta-board/*.json", ".cache/sfmta-board/**"], dest)
    snap.take()
    ... run the step ...
    snap.restore()     # every file as it was, bytes and mtime; files the step created are removed
    snap.discard()

On APFS each copy is a clonefile(2), which shares the data blocks until one
side is written, so snapshotting a 200 MB cache costs no space and a fraction
of a second. Elsewhere it falls back to shutil.copy2. The modification time is
kept, because two updaters decide what to re-read by it (a page copy older
than the sitemap's lastmod, a page copy over seven days old): a restore that
reset it to now would make a failed re-read look fresh and hide the change
from the next run.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import ctypes
import ctypes.util
import glob
import os
import shutil

try:
    _LIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    _CLONE = getattr(_LIBC, "clonefile", None)
except OSError:  # pragma: no cover - no libc to load
    _CLONE = None


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst):
        os.remove(dst)
    if _CLONE is not None and _CLONE(os.fsencode(src), os.fsencode(dst), 0) == 0:
        st = os.stat(src)
        os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))
        return
    shutil.copy2(src, dst)


def expand(root, patterns):
    """Every file under `root` a pattern matches, as sorted relative paths."""
    out = set()
    for p in patterns:
        for f in glob.glob(os.path.join(root, p), recursive=True):
            if os.path.isfile(f) and not f.endswith(".tmp"):
                out.add(os.path.relpath(f, root))
    return sorted(out)


class Snapshot(object):
    def __init__(self, root, patterns, dest):
        self.root, self.patterns, self.dir = root, list(patterns), dest
        self.files = []

    def kept(self, rel):
        """Where the snapshot keeps `rel`. A path outside the root (PIPELINE_STATE_DIR
        elsewhere) climbs with "..", which would land the copy on the file itself."""
        return os.path.join(self.dir, *[("__up__" if p == ".." else p) for p in rel.split(os.sep)])

    def take(self):
        self.discard()
        os.makedirs(self.dir, exist_ok=True)
        self.files = expand(self.root, self.patterns)
        for rel in self.files:
            _copy(os.path.join(self.root, rel), self.kept(rel))
        return self

    def changed(self):
        """Files that differ from the snapshot, were added, or were removed."""
        now = set(expand(self.root, self.patterns))
        out = sorted(now - set(self.files)) + sorted(set(self.files) - now)
        for rel in sorted(now & set(self.files)):
            a, b = os.path.join(self.root, rel), self.kept(rel)
            sa, sb = os.stat(a), os.stat(b)
            if sa.st_size != sb.st_size or sa.st_mtime_ns != sb.st_mtime_ns:
                with open(a, "rb") as fa, open(b, "rb") as fb:
                    if fa.read() != fb.read() or sa.st_mtime_ns != sb.st_mtime_ns:
                        out.append(rel)
        return sorted(set(out))

    def restore(self):
        """Put every file back as it was. Returns the paths that were restored or removed."""
        touched = self.changed()
        kept = set(self.files)
        for rel in touched:
            cur = os.path.join(self.root, rel)
            if rel in kept:
                _copy(self.kept(rel), cur)
            elif os.path.exists(cur):
                os.remove(cur)
        return touched

    def discard(self):
        if os.path.isdir(self.dir):
            shutil.rmtree(self.dir)


def _selftest():
    import tempfile
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root, dest = os.path.join(tmp, "root"), os.path.join(tmp, "snap")
        os.makedirs(os.path.join(root, "a", "b"))
        good = os.path.join(root, "a", "b", "x.json")
        with open(good, "w") as fh:
            fh.write("good")
        os.utime(good, (1_000_000_000, 1_000_000_000))
        s = Snapshot(root, ["a/**"], dest).take()
        time.sleep(0.01)
        with open(good, "w") as fh:
            fh.write("bad")
        with open(os.path.join(root, "a", "new.json"), "w") as fh:
            fh.write("new")
        assert s.changed() == ["a/b/x.json", "a/new.json"], s.changed()
        s.restore()
        assert open(good).read() == "good" and os.path.getmtime(good) == 1_000_000_000
        assert not os.path.exists(os.path.join(root, "a", "new.json"))
        assert s.changed() == []
        s.discard()
        assert not os.path.exists(dest)
    print("snapshot.py selftest ok (clonefile %s)" % ("available" if _CLONE else "unavailable"))


if __name__ == "__main__":
    _selftest()
