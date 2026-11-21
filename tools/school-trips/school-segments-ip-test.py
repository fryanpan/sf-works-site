#!/usr/bin/env python3
"""Proof of the bikeway program loop's unserved rule (tools/school-trips/school-segments-ip.py, unserved_routes) on a small
synthetic case: which promised routes a round drops when the real route search gives their pair less.

    tools/school-trips/school-segments-ip-test.py

Four routes, two budgets. Each budget's check lists its served pairs' promised routes and whether each fell short.
Rule "every" / rule "budget":

  route 0  menu route, short at $5M, fine at $10M          dropped / dropped
  route 1  traced route, short at $5M, real at $10M        kept (real at one budget, short at another) / dropped
  route 2  traced route, short at both budgets             dropped / dropped
  route 3  traced route, never promised                    kept / kept

Then the output checks (check_output) on a three-chunk case: a good output passes, and an unknown chunk id, a budget
over its cost and a budget that drops the smaller budget's chunk each fail.

Then the output checks (check_output) also fail a budget missing from BUDGETS_M, a budget with no checked car trips,
and a published file whose budgets are not nested; and the round cache's code version is stable between reads.

Light: numpy only, no data read.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ip = paths.load("school-segments-ip.py")

tag = np.array([0, 2, 1, 3], dtype=np.int16)
per_budget = [
    # $5M: three served pairs promised routes 0, 1, 2, all short
    (np.array([0, 1, 2]), np.array([True, True, True])),
    # $10M: routes 0 and 1 served in full, route 2 short
    (np.array([0, 1, 2]), np.array([False, False, True])),
]
ok = True
for rule, want in (("every", [True, False, True, False]), ("budget", [True, True, True, False])):
    got = ip.unserved_routes(4, tag, per_budget, rule)
    ok &= bool((got == np.array(want)).all())
    for r in range(4):
        print("  %s: route %d (tag %d): %s, want %s" % (rule, r, tag[r], "dropped" if got[r] else "kept", "dropped" if want[r] else "kept"))
print("unserved rule: %s" % ("pass" if ok else "FAIL"))

cost = {"a": 2.0, "b": 2.5, "c": 4.0}
B = lambda m, ids, ct=1.0: {"budgetM": m, "chunks": ids, "carTripsRemoved": ct}
good = {"nested": True, "budgets": [B(5, ["a", "b"]), B(10, ["a", "b", "c"])]}
cases = [("good", good, {}, 0),
         ("unknown id", {"nested": True, "budgets": [B(5, ["a", "x"])]}, {}, 1),
         ("over budget", {"nested": True, "budgets": [B(5, ["a", "c"])]}, {}, 1),
         ("not nested", {"nested": True, "budgets": [B(5, ["a", "b"]), B(10, ["a", "c"])]}, {}, 1),
         ("not nested, published", {"nested": False, "budgets": [B(5, ["a", "b"]), B(10, ["a", "c"])]}, {"published": True}, 1),
         ("not nested, unpublished run", {"nested": False, "budgets": [B(5, ["a", "b"]), B(10, ["a", "c"])]}, {}, 0),
         ("budget missing", good, {"budgets": (5, 10, 20)}, 1),
         ("no checked car trips", {"nested": True, "budgets": [B(5, ["a"], None)]}, {}, 1)]
for name, out, kw, n_bad in cases:
    bad = ip.check_output(out, cost, **kw)
    print("  output %s: %d failures %s, want %d" % (name, len(bad), bad, n_bad))
    ok &= len(bad) == n_bad
# the round cache's code version: a 16-character hash of the loop's source, the same on every read
v0 = ip.loop_version()
ok_v = len(v0) == 16 and v0 == ip.loop_version()
print("  loop version %s, stable on a second read: %s" % (v0, ok_v))
ok &= ok_v
# and a one-character edit to any of the hashed functions' source gives another version
import inspect
srcs = [inspect.getsource(f) for f in (ip.run, ip.unserved_routes, ip.evaluate, ip._check_job, ip.trace_routes)]
same = ip.source_hash(srcs) == v0
moved = [ip.source_hash(srcs[:i] + [s.replace("return", "return ", 1)] + srcs[i + 1:]) != v0 for i, s in enumerate(srcs)]
print("  loop version is the hash of those sources: %s; an edit to each moves it: %s" % (same, moved))
ok &= same and all(moved)
print("unserved rule and output checks: %s" % ("pass" if ok else "FAIL"))
sys.exit(0 if ok else 1)
