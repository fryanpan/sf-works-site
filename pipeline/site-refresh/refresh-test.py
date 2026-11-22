#!/usr/bin/env python3
"""Tests for the refresh's merge gate in pipeline/site-refresh/refresh.py: it merges only once every PR check has passed.

    python3 pipeline/site-refresh/refresh-test.py     # exits 1 on the first failure

No network, no gh: the check reader, the clock and the sleep are stand-ins.
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("refresh", os.path.join(HERE, "refresh.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def c(name, bucket, state=None):
    return {"name": name, "bucket": bucket, "state": state or bucket.upper()}


def fake(sequence):
    """A check reader that returns each list in turn and then repeats the last, with a clock that moves one poll per
    read."""
    t = {"now": 0.0, "i": 0}

    def read(url):
        out = sequence[min(t["i"], len(sequence) - 1)]
        t["i"] += 1
        return out

    def sleep(s):
        t["now"] += s

    return read, sleep, lambda: t["now"], t


def raises(fn, needle):
    try:
        fn()
    except R.ChecksNotPassed as e:
        assert needle in str(e), "expected %r in %r" % (needle, str(e))
        return
    raise AssertionError("expected ChecksNotPassed(%r)" % needle)


R.say = lambda msg="": None
n = 0

# The verdict on one reading.
assert R.checks_verdict([]) == ("pending", [])
assert R.checks_verdict([c("build", "pass"), c("scan", "skipping")]) == ("pass", [])
assert R.checks_verdict([c("build", "pending"), c("scan", "pass")]) == ("pending", ["build"])
assert R.checks_verdict([c("build", "fail", "FAILURE"), c("scan", "pending")])[0] == "fail"
assert R.checks_verdict([c("build", "cancel", "CANCELLED")]) == ("fail", ["build (CANCELLED)"])
n += 5

# The 2026-11-21 refresh's case: one check fails while another still runs. The gate raises and never reaches the merge.
read, sleep, clock, t = fake([[c("Secret scan", "pending"), c("Site checks", "pending")],
                              [c("Secret scan", "pass"), c("Site checks", "fail", "FAILURE"), c("Bus", "pending")]])
raises(lambda: R.wait_for_checks("pr", read=read, sleep=sleep, clock=clock), "Site checks (FAILURE)")
n += 1

# Checks that start late, run, and pass: the gate waits through every pending reading and returns.
read, sleep, clock, t = fake([[], [], [c("a", "pending"), c("b", "pending")], [c("a", "pass"), c("b", "pending")],
                              [c("a", "pass"), c("b", "pass")]])
got = R.wait_for_checks("pr", read=read, sleep=sleep, clock=clock)
assert [x["name"] for x in got] == ["a", "b"] and t["i"] == 5, t
n += 1

# No checks ever appear: main has no required checks, so an empty list is not a pass.
read, sleep, clock, t = fake([[]])
raises(lambda: R.wait_for_checks("pr", read=read, sleep=sleep, clock=clock), "no checks appeared")
assert clock() >= R.CHECKS_APPEAR
n += 1

# gh could not read the checks (None): treated as nothing yet, so it times out the same way rather than passing.
read, sleep, clock, t = fake([None])
raises(lambda: R.wait_for_checks("pr", read=read, sleep=sleep, clock=clock), "no checks appeared")
n += 1

# A check that never finishes: the gate gives up at the timeout.
read, sleep, clock, t = fake([[c("a", "pass"), c("slow", "pending")]])
raises(lambda: R.wait_for_checks("pr", read=read, sleep=sleep, clock=clock), "still running")
assert R.CHECKS_TIMEOUT <= clock() < R.CHECKS_TIMEOUT + R.CHECKS_POLL + 1
n += 1

# ship() waits before it merges: the merge call comes only after the gate, and a failed gate leaves no merge call.
calls = []
R.sh = lambda *cmd, **kw: (calls.append(cmd), (0, "abc123"))[1]
R.wait_for_checks = lambda url: (_ for _ in ()).throw(R.ChecksNotPassed("checks failed on %s: x" % url))


class P:
    returncode, stdout, stderr = 0, "https://github.com/o/r/pull/9\n", ""


R.subprocess.run = lambda *a, **kw: P()
R.STATE = os.path.join(os.environ.get("TMPDIR", "/tmp"), "refresh-test-state")
R.PENDING = os.path.join(R.STATE, "pending.json")
try:
    R.ship(["out/x.json"], "summary", "")
    raise AssertionError("ship merged past a failed gate")
except R.ChecksNotPassed:
    pass
assert not any(cmd[:3] == ("gh", "pr", "merge") for cmd in calls), calls
assert os.path.exists(R.PENDING), "the open PR must stay recorded so the next run waits"
n += 1

calls.clear()
R.wait_for_checks = lambda url: []
R.ship(["out/x.json"], "summary", "")
merge = [cmd for cmd in calls if cmd[:3] == ("gh", "pr", "merge")]
assert merge and "--auto" not in merge[0] and merge[0][-2:] == ("--match-head-commit", "abc123"), merge
n += 1
os.path.exists(R.PENDING) and os.remove(R.PENDING)

print("refresh-test: %d passed" % n)
