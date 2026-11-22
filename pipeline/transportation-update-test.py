#!/usr/bin/env python3
"""Proof that a bad increment fails its quality check, the previous data stays, and nothing downstream runs.

    pipeline/transportation-update-test.py

pipeline/README.md, rule 6: "show a quality check failing on
bad input". Each case copies one source's real data into a temporary root,
runs a stand-in fetch that writes a bad increment over it, and runs it the
way pipeline/transportation-update.py does, with that source's real checks
from pipeline/transportation-quality.py:

  truncated   the ACS extract loses six of its nine years
  null key    the newest SFMTA hearing in the mirror loses its id
  duplicated  the SFMTA Board extract repeats every bike item (a join fanning out)
  repeated    a mirror meeting lists one agenda point twice
  good        the same fetch writing the data unchanged passes and keeps it
  pipeline    the whole orchestrator: a source fails, its data and its marker
              go back, the build step after it does not run, exit 1 names the check
  held        the same failure from a step in MANUAL, in a hand run: exit 1 and
              its data goes back, but the build after it runs
  refresh     a source whose publisher did not answer keeps its copy and exits
              0: its extract is not recorded as checked, the summary names it,
              and the run exits 2, not 1
  bounded     a document source with no marker misses part of its bounded
              re-read: exit 2, its extract ages from its last good check
  retry       lib/fetch.py's read() retries a 504 with backoff and
              returns the body once it answers; a 404 is not retried
  504         the real tools/muni/muni-ewt/fetch_ridership.py against a publisher
              answering 504 every time: it retries, keeps the last good file,
              records transtat:muni-ridership failed (stale) with its last good
              check, and exits 0; the build after it runs, the run exits 2, and
              the freshness check passes today and fails two days on
  weekly      a weekly source whose refresh failed (no key on the host) is run
              again on the next run, and is skipped for its 7 days only after a
              run that passed; the freshness check holds its failed marker to
              the step's 7 days, not the daily default
  opt lines   Upgrade a Bus Line's results file loses ten of its lines
  opt grid    the same file loses one value of one line's grid
  opt month   the same file two months behind the dashboard's newest month
  mode rows   SFMTA's delivered share by mode loses its newest month
  mode share  the same file with a share over 1
  tt month    the timetable history's newest month keeps a gap for 5 lines
  muni rows   the same step writing a ridership file cut to 100 rows: its row
              check fails, the file goes back, the build is skipped, exit 1
  stale       a build step's output edited after it ran: the next run reruns
              the step though no input moved, and the run after skips it

Nothing under the real data/ or data/pipeline-state/ is written.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = paths.ROOT
TMP = tempfile.mkdtemp(prefix="pipeline-test-")
os.environ["PIPELINE_STATE_DIR"] = os.path.join(TMP, "root", "data", "pipeline-state")

tu = paths.load("transportation-update.py")
ROOT = os.path.join(TMP, "root")


def copy_in(*rels):
    for rel in rels:
        src, dst = os.path.join(REPO, rel), os.path.join(ROOT, rel)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def marker(source, version):
    path = tu.pipeline_state.PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = json.load(open(path)) if os.path.exists(path) else {}
    state[source] = {"status": "unchanged", "version": version}
    json.dump(state, open(path, "w"))


def fetch(code):
    """A stand-in fetch: a python snippet run in the test root, like a real source script."""
    return [sys.executable, "-c", "import json, os, sys\nsys.path.insert(0, %r)\nfrom lib import pipeline_state\n%s"
            % (paths.ROOT, code)]


def runner(cmd):
    import subprocess
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=dict(os.environ))
    return p.returncode, p.stdout + p.stderr


def state_of(rel):
    p = os.path.join(ROOT, rel)
    return open(p, "rb").read(), os.stat(p).st_mtime_ns


def failing(results):
    return sorted(r.check for r in results if not r.ok)


def case(name, step, rel, code, expect):
    before = state_of(rel)
    sources_before = open(tu.pipeline_state.PATH, "rb").read()
    rc, out, results, touched, restored = tu.guarded(step, fetch(code), tu.QUALITY.SPECS[step], root=ROOT,
                                                     snap_root=os.path.join(TMP, "snaps"), runner=runner)
    assert rc == 0, out
    bad = failing(results)
    if expect:
        assert expect in bad, "%s: expected %s to fail, failed: %s" % (name, expect, bad)
        assert restored and rel in touched, (restored, touched)
        assert state_of(rel) == before, "%s: %s was not put back byte for byte with its mtime" % (name, rel)
        assert open(tu.pipeline_state.PATH, "rb").read() == sources_before, "%s: source marker not put back" % name
        print("  %-10s FAIL as it should: %s; %s restored, marker restored" % (name, ", ".join(bad), rel))
    else:
        assert not bad and not restored, (name, bad)
        print("  %-10s pass as it should: %d checks, nothing restored" % (name, len(results)))


def main():
    copy_in("data/extract/census-acs", "site/data/mode-share.json", "data/sfmta-hearings",
            "data/extract/sfmta-board", "out/sfmta-board/meetings.json")
    marker("census:acs1-b08301", "2024")
    acs = "data/extract/census-acs/b08301-sf.json"

    case("truncated", "sf-mode-share", acs, """
p = %r
d = json.load(open(p)); d["records"] = d["records"][:3]
json.dump(d, open(p, "w"), indent=1)
pipeline_state.record("census:acs1-b08301", "changed", version="2025")
""" % acs, "census-acs/b08301-sf.rows")

    newest = sorted(os.listdir(os.path.join(ROOT, "data/sfmta-hearings/meetings")))[-1]
    meeting = "data/sfmta-hearings/meetings/" + newest
    case("null key", "mirror:sfmta-hearings", meeting, """
p = %r
d = json.load(open(p)); d["id"] = None
json.dump(d, open(p, "w"), indent=1)
""" % meeting, "mirror:sfmta-hearings/meetings.required[id]")

    case("repeated", "mirror:sfmta-hearings", meeting, """
p = %r
d = json.load(open(p)); d["items"] = d["items"] + d["items"][:1]
json.dump(d, open(p, "w"), indent=1)
""" % meeting, "mirror:sfmta-hearings/items.unique[item]")

    board = "data/extract/sfmta-board/since-2019-01-01.json"
    case("duplicated", "sfmta-board-records", board, """
p = %r
d = json.load(open(p)); r = d["records"][0]; r["matches"] = r["matches"] + r["matches"]
json.dump(d, open(p, "w"), indent=1)
""" % board, "sfmta-board/matches.unique[date+no+agenda+title]")

    # Jev's page dates (tools/projects/sfmta-page-dates.py): an end before its start,
    # a date that does not parse, and a short read that loses pages.
    copy_in("out/sfmta-page-dates/dates.json", "data/extract/sfmta-pages/sitemap.json")
    dates = "out/sfmta-page-dates/dates.json"
    case("end first", "sfmta-page-dates", dates, """
p = %r
d = json.load(open(p))
pg = next(x for x in d["pages"].values() if x.get("fields", {}).get("construction_start", {}).get("iso"))
pg["fields"]["construction_end"] = dict(pg["fields"]["construction_start"], iso="2001-01-31", value="2001-01")
json.dump(d, open(p, "w"), indent=1)
""" % dates, "sfmta-page-dates/end-not-before-start")

    case("bad date", "sfmta-page-dates", dates, """
p = %r
d = json.load(open(p))
pg = next(x for x in d["pages"].values() if x.get("fields", {}).get("consultation", {}).get("iso"))
pg["fields"]["consultation"]["iso"] = "2025-13-40"
json.dump(d, open(p, "w"), indent=1)
""" % dates, "sfmta-page-dates/dates.dates[iso]")

    case("lost pages", "sfmta-page-dates", dates, """
p = %r
d = json.load(open(p))
d["pages"] = dict(sorted(d["pages"].items())[:300])
json.dump(d, open(p, "w"), indent=1)
""" % dates, "sfmta-page-dates/pages.rows")

    case("date past page", "sfmta-page-dates", dates, """
p = %r
d = json.load(open(p))
pg = next(x for x in d["pages"].values() if x.get("fields", {}).get("construction_end", {}).get("iso"))
pg["latestDate"] = "2001-01-01"
json.dump(d, open(p, "w"), indent=1)
""" % dates, "sfmta-page-dates/within-page")

    case("good", "sf-mode-share", acs, """
p = %r
d = json.load(open(p)); json.dump(d, open(p + ".tmp", "w"), indent=1); os.replace(p + ".tmp", p)
""" % acs, None)

    # Upgrade a Bus Line's results (the muni-optimizer build step): a file that loses lines, or one value of one
    # line's grid, fails its checks and the published file goes back.
    opt_dir = "site/data/muni-optimizer"
    opt = opt_dir + "/" + sorted(f for f in os.listdir(os.path.join(REPO, opt_dir)) if f.endswith(".json"))[-1]
    copy_in(opt, "site/data/muni.json")
    case("opt lines", "muni-optimizer", opt, """
p = %r
d = json.load(open(p))
for l in sorted(d["lines"])[:10]:
    del d["lines"][l]
json.dump(d, open(p, "w"))
""" % opt, "muni-optimizer/lines.rows")
    case("opt grid", "muni-optimizer", opt, """
p = %r
d = json.load(open(p))
d["lines"]["22"]["grid"]["gain"].pop()
json.dump(d, open(p, "w"))
""" % opt, "muni-optimizer/grid.each")
    # one month behind the dashboard passes (the build waits there for the month's slower inputs); two doesn't
    case("opt month", "muni-optimizer", opt, """
p = %r
d = json.load(open(p))
y, m = int(d["month"][:4]), int(d["month"][5:7]) - 2
d["month"] = "%%04d-%%02d" %% ((y, m) if m > 0 else (y - 1, m + 12))
os.remove(p)
json.dump(d, open(os.path.join(os.path.dirname(p), d["month"] + ".json"), "w"))
""" % opt, "muni-optimizer/month.each")

    # The two monthly inputs of Upgrade a Bus Line, each a source step with checks of its own.
    mode, tt = "data/muni-ewt/lever/delivered_by_mode.csv", "data/muni-ewt/optimizer/timetable_month.csv"
    copy_in(mode, tt)
    case("mode rows", "muni-delivered-by-mode", mode, """
p = %r
rows = open(p, newline="").read().splitlines(keepends=True)
last = max(r.split(",")[0] for r in rows[1:])
open(p, "w", newline="").writelines(r for r in rows if not r.startswith(last + ","))
""" % mode, "muni/delivered-by-mode.rows")
    case("mode share", "muni-delivered-by-mode", mode, """
p = %r
rows = open(p, newline="").read().splitlines(keepends=True)
f = rows[-1].split(","); f[2] = "1.20000"; rows[-1] = ",".join(f)
open(p, "w", newline="").writelines(rows)
""" % mode, "muni/delivered-by-mode/share.each")
    case("tt month", "muni-timetable-history", tt, """
import csv
p = %r
rows = list(csv.DictReader(open(p, newline="")))
last, n = max(r["month"] for r in rows), 0
for r in rows:
    if r["month"] == last:
        n += 1
        if n > 5:
            r["day"] = ""
w = csv.DictWriter(open(p, "w", newline=""), fieldnames=list(rows[0]))
w.writeheader(); w.writerows(rows)
""" % tt, "muni/timetable-history/newest-month.each")

    # The orchestrator end to end: one source fails its check, the build after
    # it must not run, and the run exits 1 naming the check.
    built = os.path.join(ROOT, "out", "built.txt")
    tu.ROOT, tu.STATE, tu.SNAPSHOTS = ROOT, os.path.join(ROOT, "data/pipeline-state/steps.json"), os.path.join(TMP, "s2")
    tu.STEPS = [
        ("sf-mode-share", "source", fetch("""
p = %r
d = json.load(open(p)); d["records"] = d["records"][:2]
json.dump(d, open(p, "w"), indent=1)
pipeline_state.record("census:acs1-b08301", "changed", version="2025")
""" % acs), [], ["census-acs"], 0),
        ("a-build", "build", [sys.executable, "-c", "open(%r, 'w').write('built')" % built], ["out/built.txt"], [], 0),
    ]
    real_run = tu.run
    tu.run = lambda cmd, log=None, net=None: runner(cmd)
    before = state_of(acs)
    sys.argv = ["transportation-update.py", "--all"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            tu.main()
            code = 0
        except SystemExit as e:
            code = e.code
    out = buf.getvalue()
    assert code == 1, out
    assert "STOPPED: sf-mode-share failed quality check census-acs/b08301-sf.rows" in out, out
    assert "a-build" in out and "skipped" in out and not os.path.exists(built), out
    assert state_of(acs) == before
    st = json.load(open(tu.pipeline_state.PATH))
    assert st["census:acs1-b08301"]["version"] == "2024", st["census:acs1-b08301"]
    assert st["quality:sf-mode-share"]["status"] == "failed", st["quality:sf-mode-share"]
    assert st["step:a-build"]["status"] == "skipped"
    print("  pipeline   exit 1, build skipped, extract and marker restored, failure recorded:")
    print("             " + st["quality:sf-mode-share"]["detail"][:160])

    # The same failure from a held step (in MANUAL) in a hand run: it fails the run and keeps its previous data,
    # but the build after it runs, as it does every scheduled day on the held step's last good files.
    tu.MANUAL["sf-mode-share"] = "held for the test"
    try:
        code, out = orchestrate()
    finally:
        del tu.MANUAL["sf-mode-share"]
    assert code == 1 and "FAILED: sf-mode-share" in out and "STOPPED" not in out, out
    assert os.path.exists(built), "the build after a failing held step did not run:\n" + out
    assert state_of(acs) == before
    os.remove(built)
    print("  held       a failing MANUAL step in a hand run: exit 1, its data restored, the build after it still runs")

    # A refresh that failed: the publisher did not answer, the script kept its
    # copy, recorded its marker failed and exited 0. Checks pass on the kept
    # copy; the extract must not read as checked today.
    json.dump(dict(json.load(open(tu.pipeline_state.PATH)),
                   **{"extract:census-acs": {"checked": "2026-09-01T00:00:00", "status": "unchanged"}}),
              open(tu.pipeline_state.PATH, "w"))
    tu.STEPS = [
        ("sf-mode-share", "source", fetch("""
pipeline_state.record("census:acs1-b08301", "failed", detail="release check failed: timed out")
"""), [], ["census-acs"], 0),
    ]
    code, out = orchestrate()
    assert code == 2, (code, out)
    assert "REFRESH FAILED" in out and "census:acs1-b08301" in out and "extract:census-acs" in out, out
    assert state_of(acs) == before
    ex = json.load(open(tu.pipeline_state.PATH))["extract:census-acs"]
    assert ex["status"] == "failed" and ex["last_good"] == "2026-09-01T00:00:00", ex
    print("  refresh    exit 2, named in the summary; extract:census-acs failed, last good check kept")

    # A document source with no change marker: its bounded re-read could not
    # reach one agenda and kept the last read. The script records that through
    # pipeline_state.refreshed(); the extract must age from its last good check.
    json.dump(dict(json.load(open(tu.pipeline_state.PATH)),
                   **{"extract:sfmta-board": {"checked": "2026-09-01T00:00:00", "status": "unchanged"}}),
              open(tu.pipeline_state.PATH, "w"))
    tu.STEPS = [
        ("sfmta-board-records", "source", fetch("""
pipeline_state.refreshed("listing:sfmta-board", ["2026-09-16"])
"""), [], ["sfmta-board"], 0),
    ]
    code, out = orchestrate()
    assert code == 2, (code, out)
    assert "REFRESH FAILED" in out and "listing:sfmta-board" in out and "extract:sfmta-board" in out, out
    ex = json.load(open(tu.pipeline_state.PATH))["extract:sfmta-board"]
    assert ex["status"] == "failed" and ex["last_good"] == "2026-09-01T00:00:00", ex
    tu.STEPS[0] = ("sfmta-board-records", "source", fetch("""
pipeline_state.refreshed("listing:sfmta-board", [])
"""), [], ["sfmta-board"], 0)
    code, out = orchestrate()
    assert code == 0, (code, out)
    ex = json.load(open(tu.pipeline_state.PATH))["extract:sfmta-board"]
    assert ex["status"] != "failed" and ex["checked"] > "2026-09-01T00:00:00", ex
    print("  bounded    a document re-read that missed an agenda: exit 2, extract:sfmta-board failed from its last "
          "good check; a complete re-read records it checked")

    # read(): a transient failure is retried with backoff, anything else raised at once.
    sys.path.insert(0, HERE)
    import urllib.error
    import urllib.request
    from lib import fetch as libfetch
    calls, slept = [], []
    answers = [urllib.error.HTTPError("u", 504, "Gateway Timeout", {}, None)] * 2 + [b"body"]

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        calls.append(req.full_url)
        a = answers[len(calls) - 1]
        if isinstance(a, Exception):
            raise a
        return Resp(a)
    real_urlopen, real_sleep = urllib.request.urlopen, libfetch.time.sleep
    urllib.request.urlopen, libfetch.time.sleep = fake, slept.append
    try:
        with redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            assert libfetch.read("https://example.invalid/x") == b"body" and len(calls) == 3 and slept == [5, 20], (calls, slept)
            calls[:], slept[:] = [], []
            answers[:] = [urllib.error.HTTPError("u", 404, "Not Found", {}, None)]
            try:
                libfetch.read("https://example.invalid/x")
                raise AssertionError("404 not raised")
            except urllib.error.HTTPError as e:
                assert e.code == 404 and len(calls) == 1 and not slept, (calls, slept)
    finally:
        urllib.request.urlopen, libfetch.time.sleep = real_urlopen, real_sleep
    assert libfetch.is_transient(urllib.error.URLError(TimeoutError("timed out")))
    assert not libfetch.is_transient(ValueError("bad json"))
    print("  retry      two 504s then an answer: 3 requests, waits of 5 and 20 s; a 404 raised at once")

    # The real muni-ridership fetch against a publisher that answers 504 every time.
    copy_in("data/muni-ewt/ridership.csv", "data/muni-ewt/weekday_boardings_published.csv")
    ride = "data/muni-ewt/ridership.csv"
    shim = os.path.join(TMP, "shim")
    os.makedirs(shim)
    hits = os.path.join(TMP, "hits.txt")
    open(os.path.join(shim, "sitecustomize.py"), "w").write("""
import time, urllib.error, urllib.request
time.sleep = lambda s: None
def urlopen(req, *a, **k):
    open(%r, "a").write("x")
    raise urllib.error.HTTPError(getattr(req, "full_url", req), 504, "Gateway Timeout", {}, None)
urllib.request.urlopen = urlopen
""" % hits)
    built3 = os.path.join(ROOT, "out", "built3.txt")
    build3 = ("a-build", "build", [sys.executable, "-c", "open(%r, 'w').write('built')" % built3], ["out/built3.txt"], [], 0)
    st = json.load(open(tu.pipeline_state.PATH))
    st.pop("transtat:muni-ridership", None)
    st["step:muni-ridership"] = {"checked": "2026-11-10T16:00:00", "status": "unchanged"}
    json.dump(st, open(tu.pipeline_state.PATH, "w"))
    tu.STEPS = [("muni-ridership", "source", [sys.executable, paths.script("fetch_ridership.py"),
                                              "--update"], [ride, "data/muni-ewt/weekday_boardings_published.csv"], [], 0),
                build3]
    before = state_of(ride)
    os.environ["PYTHONPATH"] = shim
    try:
        code, out = orchestrate()
    finally:
        del os.environ["PYTHONPATH"]
    assert code == 2, (code, out)
    assert open(hits).read() == "xxxx", "expected 4 tries, got %d" % len(open(hits).read())
    assert "REFRESH FAILED" in out and "transtat:muni-ridership" in out and "STOPPED" not in out, out
    assert os.path.exists(built3), "the build after a stale source did not run:\n" + out
    assert state_of(ride)[0] == before[0]
    st = json.load(open(tu.pipeline_state.PATH))
    m = st["transtat:muni-ridership"]
    assert m["status"] == "failed" and m["last_good"] == "2026-11-10T16:00:00" and "stale" in m["detail"], m
    assert st["quality:muni-ridership"]["status"] == "passed", st["quality:muni-ridership"]
    fr = paths.load("refresh-freshness.py")
    import datetime as dt
    named = lambda now: {n for n, *_ in fr.stale(dt.datetime.fromisoformat(now), st)}
    assert "transtat:muni-ridership" not in named("2026-11-11T17:00:00")
    assert "transtat:muni-ridership" in named("2026-11-13T17:00:00")
    print("  504        4 tries, last good file kept, marker failed (stale) from 2026-11-10, build ran, exit 2; "
          "freshness passes on 11-11 and fails on 11-13")

    # A weekly source with no key on the host: it keeps its copy and records its marker failed, like
    # tools/street-safety/telraam-sf.py --update without TELRAAM_API_KEY.
    key = os.path.join(TMP, "key")
    tu.STEPS = [("muni-ridership", "source", fetch("""
ok = os.path.exists(%r)
pipeline_state.record("weekly:test", "unchanged" if ok else "failed", detail=None if ok else "no key on this host")
""" % key), [ride], [], 7)]
    code, out = orchestrate(all_=False)
    assert code == 2 and "weekly:test" in out and "skipped" not in out, (code, out)
    st = json.load(open(tu.pipeline_state.PATH))
    assert st["weekly:test"]["status"] == "failed" and st["weekly:test"]["step"] == "muni-ridership", st["weekly:test"]
    # Markers are stamped to the second, and a failure recorded in the same second as the last one reads as the
    # earlier step's (refresh_failures); real runs are hours apart.
    import time
    time.sleep(1.1)
    code, out = orchestrate(all_=False)
    assert code == 2 and "skipped" not in out, "a failed weekly source was not retried on the next run:\n" + out
    assert json.load(open(tu.pipeline_state.PATH))["weekly:test"]["step"] == "muni-ridership"
    open(key, "w").write("k")
    code, out = orchestrate(all_=False)
    assert code == 0 and "skipped" not in out and "REFRESH FAILED" not in out, (code, out)
    assert json.load(open(tu.pipeline_state.PATH))["weekly:test"]["status"] == "unchanged"
    code, out = orchestrate(all_=False)
    assert code == 0 and "skipped: ran" in out and "runs at most every 7 day(s)" in out, (code, out)
    # Freshness, on the real step table: a failed marker of the weekly telraam step is held to 7 days, an extract to
    # its step's interval, and a marker no step has named to the daily default.
    tel = lambda **k: {"telraam:segments": dict({"checked": "2026-11-20T14:38:00", "status": "failed", "step": "telraam"}, **k)}
    at = lambda now, state: [(n, d) for n, d, _ in fr.stale(dt.datetime.fromisoformat(now), state) if n in state]
    assert fr.TU.interval_days("telraam") == 7
    assert at("2026-11-20T17:00:00", tel()) == [("telraam:segments", 7)]
    assert at("2026-11-20T17:00:00", tel(last_good="2026-11-10T14:00:00")) == []
    assert at("2026-11-20T17:00:00", tel(last_good="2026-11-05T14:00:00")) == [("telraam:segments", 7)]
    assert at("2026-11-20T17:00:00", {"other:x": {"checked": "2026-11-20T14:00:00", "status": "failed",
                                                   "last_good": "2026-11-17T14:00:00"}}) == [("other:x", 1)]
    assert fr.TU.source_interval_days("extract:census-acs", {}) == 1
    print("  weekly     a weekly source that failed is retried on the next run and skipped once it has passed; "
          "its failed marker is held to its step's 7 days, not 1")

    # The same step with new data that fails its row check still stops the run.
    os.remove(built3)
    tu.STEPS = [("muni-ridership", "source", fetch("""
p = %r
lines = open(p).read().splitlines(True)
open(p, "w").write("".join(lines[:101]))
""" % ride), [ride], [], 0), build3]
    code, out = orchestrate()
    assert code == 1, (code, out)
    assert "STOPPED: muni-ridership failed quality check muni/ridership.rows" in out, out
    assert not os.path.exists(built3) and state_of(ride)[0] == before[0], out
    print("  muni rows  a 100-row ridership file: muni/ridership.rows fails, file restored, build skipped, exit 1")

    # A stale output: the build's output is edited after it ran.
    tu.run = real_run
    inp, outp = os.path.join(ROOT, "in.txt"), os.path.join(ROOT, "out", "built2.txt")
    open(inp, "w").write("x")
    tu.STEPS = [("b-build", "build", [sys.executable, "-c",
                                      "open(%r, 'w').write(open(%r).read() * 2)" % (outp, inp)], ["out/built2.txt"], [], 0)]
    code, out = orchestrate(all_=False)
    assert code == 0 and open(outp).read() == "xx", out
    code, out = orchestrate(all_=False)
    assert "skipped: 1 inputs and 1 outputs unchanged" in out, out
    open(outp, "w").write("hand edit")
    code, out = orchestrate(all_=False)
    assert "reruns: 1 output(s) differ" in out and open(outp).read() == "xx", out
    code, out = orchestrate(all_=False)
    assert "skipped" in out, out
    print("  stale      an edited output reruns its step; the run after skips it")
    shutil.rmtree(TMP)
    print("transportation-update-test: all cases ok")


def orchestrate(all_=True):
    sys.argv = ["transportation-update.py"] + (["--all"] if all_ else [])
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            tu.main()
            code = 0
        except SystemExit as e:
            code = e.code
    return code, buf.getvalue()


if __name__ == "__main__":
    main()
