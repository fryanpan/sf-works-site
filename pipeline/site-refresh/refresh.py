#!/usr/bin/env python3
"""The scheduled site refresh on the GCP VM: refresh every source, rebuild what changed, ship it through a PR.

    pipeline/site-refresh/run.sh           # what the systemd timer runs: resets to origin/main, then this
    python3 pipeline/site-refresh/refresh.py --no-ship   # everything but the commit, push and PR

Runs on the cloud VM from a clone of this repo, daily at 13:15 UTC (pipeline/site-refresh/sf-works-refresh.timer),
never on a laptop. In order:

  1. Refuses to start while the last run's pull request is still open, so two runs never race one change.
  2. pipeline/transportation-update.py --scheduled: every source step asks its publisher whether anything changed and
     re-reads only that, each followed by its quality checks; every build whose inputs moved reruns. MANUAL steps
     (the School Trips model builds) are left out.
  3. pipeline/refresh-freshness.py: every step's last good check inside its update interval.
  4. When tracked files changed: a branch data-refresh/<date>, staged file by file (never `git add -A`), a pull
     request, a wait for every check on it (.github/workflows/checks.yml) to finish, and only when every one has
     passed, its squash merge, which deploys sf-works.org through .github/workflows/deploy.yml. When nothing
     changed, nothing is committed and nothing deploys.

A change merges once its automatic checks pass.
The refresh of 2026-11-21 merged its pull request before its checks finished and broke main, so the merge now waits: a check
that fails, no checks appearing, or checks still running after CHECKS_TIMEOUT leaves the pull request open and alerts.
The next run then refuses to start until somebody merges or closes it (step 1). Never `gh pr merge --auto`.

A failed quality check (transportation-update exits 1), a failed freshness check, a write outside the pipeline's
output directories, a failed or unfinished check on the pull request, or a failed push or merge opens a GitHub issue labelled data-refresh (or comments on the open
one) in the ALERT_REPO setting's repo, or this one when that is unset. The orchestrator has already put the failing
source's previous data back, and nothing is pushed, so the site keeps the last good data.

Every run's full output is kept on the VM, one log file per run, and never in an issue, commit or PR. The 511 token and the
Muni archive under ~/muni-511 are never read here; a Muni step registered in STEPS reads them itself.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import pipeline_state, settings  # noqa: E402

STATE = os.path.expanduser("~/.local/state/sf-works-refresh")
PENDING = os.path.join(STATE, "pending.json")
LABEL = "data-refresh"
# Where the alerts and the heartbeat go: the ALERT_REPO setting (owner/name, lib/settings.py), else this clone's own
# repo. A run's log tail goes into the alert, so the VM points this at a private repo, which also holds the dead-man
# workflow that reads the heartbeat.
ALERT_REPO = settings.get("ALERT_REPO")
# Where the pipeline writes. A changed tracked file anywhere else is a step writing where it should not, and stops
# the ship rather than reaching main.
OUTPUTS = ("out/", "site/data/", "data/")

# The PR's checks: how long to wait for them to finish, how often to look, and how long to wait for the first one
# to appear. main requires its repo and build checks (.github/workflows/checks.yml), and the wait covers every check
# on the PR, required or not; an empty list must not read as passed. A passing run of PR checks took
# 21 minutes on 2026-11-21 (#577, "Site checks, tests, import cycles, build"), so the wait allows about three times that.
CHECKS_TIMEOUT = 60 * 60
CHECKS_POLL = 30
CHECKS_APPEAR = 5 * 60

LOG = None


class ChecksNotPassed(RuntimeError):
    """The pull request's checks failed, never appeared, or did not finish in time; the PR stays open."""


def say(msg=""):
    print(msg, flush=True)
    if LOG:
        LOG.write(msg + "\n")
        LOG.flush()


def sh(*cmd, check=True, quiet=False):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if not quiet and out:
        say(out)
    if check and p.returncode:
        raise RuntimeError("%s exited %d: %s" % (" ".join(cmd[:3]), p.returncode, out[-800:]))
    return p.returncode, out


def gh_ok():
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def gh_alert(*args):
    """A gh command against the alert repo."""
    return ("gh", *args, *(("-R", ALERT_REPO) if ALERT_REPO else ()))


def alert(title, body):
    """Open the data-refresh issue, or comment on the open one, so one outage is one issue."""
    say("ALERT: " + title)
    text = "%s\n\nFrom the scheduled site refresh (pipeline/site-refresh/refresh.py).\n\n```\n%s\n```" % (title, body[-6000:])
    if not gh_ok():
        say("gh is not authenticated on this VM, so the alert stays in the run log only")
        return
    subprocess.run(gh_alert("label", "create", LABEL, "--color", "efb118", "--description", "Scheduled data refresh"),
                   cwd=ROOT, capture_output=True)
    _, out = sh(*gh_alert("issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1"),
                check=False, quiet=True)
    try:
        open_issue = (json.loads(out) or [{}])[0].get("number")
    except ValueError:
        open_issue = None
    if open_issue:
        sh(*gh_alert("issue", "comment", str(open_issue), "--body", text), check=False)
    else:
        sh(*gh_alert("issue", "create", "--label", LABEL, "--title", "Data refresh failed: " + title, "--body", text),
           check=False)


def heartbeat():
    """Record this good run where GitHub can see it: the data-refresh label's description carries its time.
    A dead-man workflow in the alert repo opens an issue when that time is over two days old, which catches the case no
    run can report itself: the VM down, the timer stopped, or the token expired."""
    if not gh_ok():
        return
    subprocess.run(gh_alert("label", "create", LABEL, "--color", "efb118", "--description", "Scheduled data refresh"),
                   cwd=ROOT, capture_output=True)
    sh(*gh_alert("label", "edit", LABEL, "--description",
                 "Scheduled data refresh; last good run %s" % dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")),
       check=False, quiet=True)


def previous_pr_open():
    try:
        pending = json.load(open(PENDING))
    except (FileNotFoundError, ValueError):
        return None
    if not gh_ok():
        return pending
    _, out = sh("gh", "pr", "view", str(pending["pr"]), "--json", "state", check=False, quiet=True)
    try:
        state = json.loads(out)["state"]
    except (ValueError, KeyError):
        return pending
    if state == "OPEN":
        return pending
    os.remove(PENDING)
    if state == "CLOSED":
        # Closed without merging: somebody rejected that data. Carrying it over would ship it again tomorrow.
        return {"rejected": pending["pr"]}
    return None


def changed_files(against=None):
    """Every path that differs from HEAD (or from `against`), and every new file not ignored, by name."""
    def z(*cmd):
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True).stdout.decode("utf-8", "surrogateescape")
        return [x for x in out.split("\0") if x]
    if against:
        return sorted(set(z("git", "diff", "--name-only", "-z", against))
                      | set(z("git", "ls-files", "--others", "--exclude-standard", "-z")))
    entries, files = z("git", "status", "--porcelain", "-z", "--untracked-files=all"), []
    i = 0
    while i < len(entries):
        e = entries[i]
        files.append(e[3:])
        i += 2 if e[0] in "RC" else 1  # a rename carries its old path as the next entry
    return sorted(files)


def sync_to_main(carry_over=True):
    """Bring the clone to origin/main, carrying over pipeline output the last run made that main has not taken.

    A run that stopped (a failed check, a failed push or merge, a PR closed unmerged, a crash) leaves its new data in
    the tree or on a data-refresh branch while data/pipeline-state/ already records it as read, so dropping it would
    lose that data until the source changes again. So every output path that differs from origin/main is kept, unless
    main itself changed that path since the commit this clone last built on: then main's copy wins, which is also the
    case for a refresh PR that merged. Anything outside the output directories is reset. Returns the paths carried."""
    _, base = sh("git", "merge-base", "HEAD", "origin/main", quiet=True, check=False)
    main_moved = set(changed_files_between(base.strip(), "origin/main")) if base.strip() else set()
    carry = [f for f in changed_files(against="origin/main") if f.startswith(OUTPUTS) and f not in main_moved] \
        if carry_over else []
    saved = {}
    for f in carry:
        path = os.path.join(ROOT, f)
        saved[f] = open(path, "rb").read() if os.path.isfile(path) else None
    sh("git", "checkout", "-q", "-f", "-B", "main", "origin/main")
    sh("git", "clean", "-fdq")
    for f, data in saved.items():
        path = os.path.join(ROOT, f)
        if data is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(data)
    return carry


def changed_files_between(a, b):
    out = subprocess.run(["git", "diff", "--name-only", "-z", a, b], cwd=ROOT, capture_output=True).stdout
    return [x for x in out.decode("utf-8", "surrogateescape").split("\0") if x]


def checks_verdict(checks):
    """("pass" | "fail" | "pending", names) for the checks `gh pr checks --json name,bucket,state` lists.

    pass: at least one check, and every one passed or was skipped. fail: any failed or was cancelled (names lists
    them). pending: none yet, or some still running."""
    if not checks:
        return "pending", []
    bad = sorted("%s (%s)" % (c.get("name"), c.get("state")) for c in checks if c.get("bucket") in ("fail", "cancel"))
    if bad:
        return "fail", bad
    waiting = sorted(c.get("name") for c in checks if c.get("bucket") not in ("pass", "skipping"))
    if waiting:
        return "pending", waiting
    return "pass", []


def read_checks(url):
    """The PR's checks as a list, or None when gh could not read them (counted as still pending)."""
    p = subprocess.run(["gh", "pr", "checks", url, "--json", "name,bucket,state"], cwd=ROOT, capture_output=True,
                       text=True)
    # gh exits 8 while checks are pending and 1 when one failed; the JSON is printed either way.
    try:
        return json.loads(p.stdout or "null")
    except ValueError:
        return None


def wait_for_checks(url, read=read_checks, sleep=time.sleep, clock=time.monotonic,
                    timeout=CHECKS_TIMEOUT, poll=CHECKS_POLL, appear=CHECKS_APPEAR):
    """Block until every check on the PR has passed. Raises ChecksNotPassed when one fails, when none has appeared
    after `appear` seconds, or when some are still running after `timeout` seconds."""
    start = clock()
    while True:
        checks = read(url)
        verdict, names = checks_verdict(checks or [])
        if verdict == "pass":
            say("every check passed on %s: %s" % (url, ", ".join(sorted(c.get("name") for c in checks))))
            return checks
        if verdict == "fail":
            raise ChecksNotPassed("checks failed on %s: %s" % (url, ", ".join(names)))
        waited = clock() - start
        if not checks and waited >= appear:
            raise ChecksNotPassed("no checks appeared on %s in %d minutes" % (url, appear // 60))
        if waited >= timeout:
            raise ChecksNotPassed("checks still running on %s after %d minutes: %s"
                                  % (url, timeout // 60, ", ".join(names)))
        sleep(poll)


def ship(files, summary, refresh_failed):
    today = dt.date.today().isoformat()
    branch = "data-refresh/%s" % dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    sh("git", "checkout", "-q", "-b", branch)
    for i in range(0, len(files), 200):
        sh("git", "add", "--", *files[i:i + 200], quiet=True)
    msg = ("Data refresh %s: %d files from the scheduled run\n\n%s\n\nRun by pipeline/site-refresh/run.sh.\n"
           % (today, len(files), summary))
    sh("git", "commit", "-q", "-m", msg)
    sh("git", "push", "-q", "origin", branch)
    body = ("The scheduled daily refresh on the GCP VM found new data and rebuilt what it feeds.\n\n%s\n\n%s"
            "Every source passed its quality checks and every step is inside its update interval "
            "(pipeline/refresh-freshness.py). Merged by the refresh once every check on this PR has passed "
            "(a change merges once its automatic checks pass); a failed check leaves it open and alerts. The "
            "merge deploys sf-works.org.\n\n"
            "Generated with [Claude Code](https://claude.com/claude-code) by pipeline/site-refresh/refresh.py\n" % (
                "```\n" + summary + "\n```",
                ("Sources whose publisher did not answer kept their last good copy:\n```\n%s\n```\n\n" % refresh_failed)
                if refresh_failed else ""))
    p = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title",
                        "Data refresh %s" % today, "--body", body], cwd=ROOT, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError("gh pr create exited %d: %s" % (p.returncode, p.stderr[-800:]))
    url = next(l for l in p.stdout.split() if l.startswith("https://github.com/"))
    say("opened " + url)
    os.makedirs(STATE, exist_ok=True)
    json.dump({"pr": url.rsplit("/", 1)[-1], "branch": branch, "opened": today}, open(PENDING, "w"))
    _, head = sh("git", "rev-parse", "HEAD", quiet=True)
    # Raises ChecksNotPassed and leaves the PR open, PENDING in place, so the next run waits for a person.
    wait_for_checks(url)
    # --match-head-commit: merge only the commit whose checks just passed.
    sh("gh", "pr", "merge", url, "--squash", "--delete-branch", "--match-head-commit", head.strip())
    say("merged " + url)
    os.remove(PENDING)
    sh("git", "fetch", "-q", "origin")
    sh("git", "checkout", "-q", "main")
    sh("git", "reset", "-q", "--hard", "origin/main")
    sh("git", "branch", "-q", "-D", branch, check=False)
    return url


RUNNING = os.path.join(STATE, "running")


def main():
    """Lock, log, and run; a run that did not get to finish is noticed by the next one through RUNNING."""
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ship", action="store_true", help="refresh and check, commit nothing")
    a = ap.parse_args()
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    lock = open(os.path.join(STATE, "lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another refresh is running; this one stops")
        return 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    LOG = open(os.path.join(STATE, "logs", "%s.log" % stamp), "a")
    _, head = sh("git", "log", "--oneline", "-1", quiet=True)
    say("site refresh %s at %s" % (stamp, head))
    killed = os.path.exists(RUNNING) and not os.environ.get("SF_REFRESH_REEXEC")
    open(RUNNING, "w").write(stamp)
    try:
        code = run(a, lock, killed)
    except Exception:
        import traceback
        # RUNNING stays, so the next run treats this one as killed and starts from clean state.
        alert("the refresh crashed", traceback.format_exc())
        return 1
    os.remove(RUNNING)
    return code


def run(a, lock, killed):
    pending = previous_pr_open()
    if pending and "rejected" not in pending:
        alert("the last refresh's pull request #%s is still open" % pending["pr"],
              "A new run would rebuild on main without that change. Merge or close it, then the next run proceeds.")
        return 1
    carry_over = True
    if pending:
        say("pull request #%s was closed without merging: its data is dropped, not carried over" % pending["rejected"])
        carry_over = False
    if pending or killed:
        # Either way this run's data/pipeline-state markers describe data that is no longer in the tree, so they go
        # too: every source is re-read in full and every step rebuilt, against main's copy.
        state_dir = os.path.join(ROOT, "data", "pipeline-state")
        for f in ("sources.json", "steps.json"):
            if os.path.exists(os.path.join(state_dir, f)):
                os.replace(os.path.join(state_dir, f), os.path.join(state_dir, f + ".dropped"))
    if killed:
        # The last run was killed (a timeout, a reboot, a crash): a step may have stopped mid-write with its source
        # already marked read, and nothing checked what it left. Drop its leftovers and every marker, so this run
        # re-reads every source in full and rebuilds every step.
        carry_over = False
        alert("the last refresh did not finish; this run re-reads every source from scratch",
              "Its leftovers were dropped and data/pipeline-state/{sources,steps}.json moved to *.dropped.")
    me = open(os.path.abspath(__file__), "rb").read()
    carried = sync_to_main(carry_over)
    if carried:
        say("carried over %d output file(s) from the last run that main has not taken: %s"
            % (len(carried), ", ".join(carried[:8]) + (" ..." if len(carried) > 8 else "")))
    if open(os.path.abspath(__file__), "rb").read() != me and not os.environ.get("SF_REFRESH_REEXEC"):
        # main brought a new version of this script: run that one, on the tree just synced.
        LOG.close()
        lock.close()
        os.environ["SF_REFRESH_REEXEC"] = "1"
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])

    # A listed project whose end has passed since the list was built: coordination-projects judges ends against the
    # day it runs, but a build whose inputs are unchanged does not run, so force it today. The scheduled run below then
    # rebuilds whatever reads the new list.
    import importlib.util
    tq = paths.load("transportation-quality.py", "tq")
    ended = tq.finished_listed()
    if ended:
        say("%d listed project(s) have ended since the list was built (%s); rebuilding it first"
            % (len(ended), ", ".join(ended[:5])))
        fp = subprocess.run([sys.executable, "pipeline/transportation-update.py", "--only", "coordination-projects",
                             "--all"], cwd=ROOT, capture_output=True, text=True, env=dict(os.environ, PYTHONUNBUFFERED="1"))
        say(fp.stdout.strip())
        if fp.returncode not in (0, 2):
            alert("rebuilding the project list for ended projects failed", fp.stdout + fp.stderr)
            return 1
    p = subprocess.Popen([sys.executable, "pipeline/transportation-update.py", "--scheduled"], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         env=dict(os.environ, PYTHONUNBUFFERED="1"))
    lines = []
    for line in p.stdout:
        lines.append(line.rstrip("\n"))
        say(line.rstrip("\n"))
    code = p.wait()
    out = "\n".join(lines)
    if code not in (0, 2):
        stopped = [l for l in lines if l.startswith("STOPPED") or "FAILED" in l]
        alert((stopped[-1] if stopped else "transportation-update exited %d" % code)[:200], out)
        return 1
    pipeline_state.record("run:scheduled", "changed" if code == 0 else "checked",
                          detail="transportation-update.py --scheduled exited %d" % code)

    fp = subprocess.run([sys.executable, "pipeline/refresh-freshness.py"], cwd=ROOT, capture_output=True, text=True)
    say(fp.stdout.strip())
    if fp.returncode:
        alert("freshness check failed", fp.stdout)
        return 1

    files = changed_files()
    stray = [f for f in files if not f.startswith(OUTPUTS)]
    if stray:
        alert("the run wrote outside the pipeline's output directories", "\n".join(stray[:50]))
        return 1
    if not files:
        say("no tracked file changed: nothing to commit, nothing to deploy")
        heartbeat()
        return 0
    summary_start = next((i for i, l in enumerate(lines) if " files changed in " in l), len(lines))
    summary = "\n".join(lines[summary_start:summary_start + 30])
    refresh_failed = "\n".join(l for l in lines[summary_start:] if l.startswith("  ") and "REFRESH" not in l) \
        if any(l.startswith("REFRESH FAILED") for l in lines) else ""
    say("%d files changed: %s" % (len(files), ", ".join(files[:8]) + (" ..." if len(files) > 8 else "")))
    if a.no_ship:
        say("--no-ship: leaving the changes in the working tree")
        return 0
    if not gh_ok():
        alert("gh is not authenticated on the VM, so the change cannot ship", "\n".join(files[:50]))
        return 1
    try:
        ship(files, summary, refresh_failed)
    except ChecksNotPassed as e:
        alert("the refresh's pull request did not pass its checks and was left open",
              "%s\n\nNothing merged, so main and sf-works.org keep the last good data. Fix the cause, then merge or "
              "close the pull request; the next run waits until then." % e)
        return 1
    except RuntimeError as e:
        # The commit stays on its branch; the next run's sync_to_main carries its files back over main.
        alert("shipping the refresh failed", str(e))
        return 1
    heartbeat()
    return 0


if __name__ == "__main__":
    sys.exit(main())
