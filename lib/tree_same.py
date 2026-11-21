#!/usr/bin/env python3
"""Whether two copies of an output tree hold the same data, allowing only run-date stamps and float rounding.

    python3 lib/tree_same.py BASE NEW      # exit 1 when any file differs in data
    python3 lib/tree_same.py --selftest

tools/school-trips/school-trips-vm.sh's precheck: the light steps rerun on a commit's own outputs must reproduce them. Byte
equality is too strict for two reasons seen on 2026-10-23 (sim-precheck-snap1020b): several steps stamp the run's
date ("queried 2026-10-23", "victimsFetched": "2026-10-23"), and a file last built on the Mac differs from a Linux
rebuild in the last digit of a float (1.4e-15 relative at most). So a JSON file passes when its structure, every
non-date string and every integer are equal, every float is within FLOAT_REL, and a string differs only where both
sides hold a YYYY-MM-DD date. Anything else, and any non-JSON file, must match byte for byte. Each tolerated file is
printed with what was tolerated, so the record says what the precheck let through.
"""

import json
import math
import os
import re
import sys
import tempfile

FLOAT_REL = 1e-9
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _strip_dates(s):
    return DATE.sub("<date>", s)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compare(a, b, path, tolerated, problems):
    if _num(a) and _num(b) and (isinstance(a, float) or isinstance(b, float)):
        if a != b:
            if not (math.isfinite(a) and math.isfinite(b)):   # NaN or infinity: only the same token passes
                if repr(float(a)) != repr(float(b)):
                    problems.append("%s: %r vs %r" % (path, a, b))
                return
            rel = abs(a - b) / max(abs(a), abs(b))
            if rel > FLOAT_REL:
                problems.append("%s: %r vs %r" % (path, a, b))
            else:
                tolerated["float"] = max(tolerated.get("float", 0.0), rel)
        return
    if type(a) is not type(b):
        problems.append("%s: %r vs %r" % (path, a, b))
        return
    if isinstance(a, dict):
        if set(a) != set(b):
            problems.append("%s: keys %s" % (path, sorted(set(a) ^ set(b))[:5]))
            return
        for k in a:
            compare(a[k], b[k], "%s.%s" % (path, k), tolerated, problems)
    elif isinstance(a, list):
        if len(a) != len(b):
            problems.append("%s: length %d vs %d" % (path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, "%s[%d]" % (path, i), tolerated, problems)
    elif isinstance(a, str):
        if a != b:
            if _strip_dates(a) == _strip_dates(b) and DATE.search(a):
                tolerated.setdefault("dates", []).append(path)
            else:
                problems.append("%s: %r vs %r" % (path, a[:80], b[:80]))
    elif a != b:
        problems.append("%s: %r vs %r" % (path, a, b))


def files(top):
    out = set()
    for d, _, names in os.walk(top):
        out.update(os.path.relpath(os.path.join(d, n), top) for n in names)
    return out


def same_trees(base, new, out=sys.stdout):
    """Print one line per file that is not byte-identical; return True when every one holds the same data."""
    ok = True
    a, b = files(base), files(new)
    for rel in sorted(a ^ b):
        print("DIFFERENT %s: only in %s" % (rel, "base" if rel in a else "new"), file=out)
        ok = False
    for rel in sorted(a & b):
        pa, pb = os.path.join(base, rel), os.path.join(new, rel)
        with open(pa, "rb") as f, open(pb, "rb") as g:
            ba, bb = f.read(), g.read()
        if ba == bb:
            continue
        problems, tolerated = [], {}
        try:
            compare(json.loads(ba), json.loads(bb), "", tolerated, problems)
        except ValueError:
            problems.append("not JSON, and the bytes differ")
        if problems:
            print("DIFFERENT %s: %s" % (rel, "; ".join(problems[:3])), file=out)
            ok = False
        else:
            print("tolerated %s: %s" % (rel, ", ".join(
                "dates at %d paths (%s)" % (len(v), v[0]) if k == "dates" else "floats within %.1e" % v
                for k, v in sorted(tolerated.items()))), file=out)
    return ok


def selftest():
    import io
    t = tempfile.mkdtemp()
    base, new = os.path.join(t, "a"), os.path.join(t, "b")
    for d in (base, new):
        os.makedirs(d)
    cases = {
        "same.json": ({"x": 1}, {"x": 1}, True),
        "dates.json": ({"q": "[DataSF x — queried 2026-10-22]"}, {"q": "[DataSF x — queried 2026-10-23]"}, True),
        "float.json": ({"p": 0.18263161169346337}, {"p": 0.18263161169346334}, True),
        "value.json": ({"n": 612.1}, {"n": 612.2}, False),
        "text.json": ({"s": "Balboa"}, {"s": "Burton"}, False),
        "int.json": ({"n": 3}, {"n": 4}, False),
        "keys.json": ({"a": 1}, {"b": 1}, False),
        "inf.json": ({"x": 1.0}, {"x": float("inf")}, False),
    }
    for want in (True, False):
        for d in (base, new):
            for f in os.listdir(d):
                os.remove(os.path.join(d, f))
        for name, (x, y, ok) in cases.items():
            if ok == want or ok:
                json.dump(x, open(os.path.join(base, name), "w"))
                json.dump(y, open(os.path.join(new, name), "w"))
        buf = io.StringIO()
        got = same_trees(base, new, buf)
        assert got is want, (want, buf.getvalue())
        if want:
            assert "tolerated dates.json: dates at 1 paths" in buf.getvalue(), buf.getvalue()
            assert "tolerated float.json: floats within" in buf.getvalue(), buf.getvalue()
        else:
            for name in ("value.json", "text.json", "int.json", "keys.json", "inf.json"):
                assert "DIFFERENT " + name in buf.getvalue(), buf.getvalue()
    open(os.path.join(base, "x.txt"), "w").write("a\n")
    open(os.path.join(new, "x.txt"), "w").write("b\n")
    assert not same_trees(base, new, io.StringIO())
    print("tree_same selftest: dates and float rounding tolerated; a changed value, string, integer, key or "
          "non-JSON file fails")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__.split("\n")[2].strip())
    sys.exit(0 if same_trees(sys.argv[1], sys.argv[2]) else 1)
