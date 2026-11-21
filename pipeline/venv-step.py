#!/usr/bin/env python3
"""Run a pipeline script in the analysis virtualenv (numpy, GrowBikeNet, Pillow), or record that the virtualenv is missing and keep the script's last outputs.

    pipeline/venv-step.py growbikenet-order.py --crashes

pipeline/transportation-update.py runs every step whose script needs numpy,
GrowBikeNet or Pillow through this, since the interpreter that runs the
orchestrator has none of them (Homebrew's python3 moved to 3.14 on 2026-10-02
and numpy did not come with it). The virtualenv is $SF_WORKS_VENV, or
~/.venvs/sf-works-geo; pipeline/requirements-geo.txt and pipeline/requirements-refresh.txt pin it and say how to
build it.

When the virtualenv is missing, or cannot import what the requirements name,
nothing runs: the step's outputs stay as they are, "venv:sf-works-geo" is
recorded as failed in data/pipeline-state/sources.json, and this exits 0. The
orchestrator names that marker under REFRESH FAILED, exits 2, and does not
record the step as built, so it runs again once the virtualenv is back.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state  # noqa: E402

VENV = os.environ.get("SF_WORKS_VENV") or os.path.expanduser("~/.venvs/sf-works-geo")
MARKER = "venv:sf-works-geo"
NEEDS = "import numpy, PIL, geopandas, osmnx, growbikenet, duckdb"
BUILD = "python3.13 -m venv %s && %s/bin/pip install -r pipeline/requirements-geo.txt -r pipeline/requirements-refresh.txt" % (VENV, VENV)


def main():
    if len(sys.argv) < 2 or not sys.argv[1].endswith(".py"):
        sys.exit("usage: pipeline/venv-step.py <script.py> [args]")
    py = os.path.join(VENV, "bin", "python")
    problem = None
    if not os.path.exists(py):
        problem = "no virtualenv at %s" % VENV
    else:
        p = subprocess.run([py, "-c", NEEDS], capture_output=True, text=True)
        if p.returncode:
            problem = "%s cannot %s: %s" % (py, NEEDS, (p.stderr.strip().splitlines() or ["?"])[-1])
    if problem:
        pipeline_state.record(MARKER, "failed", detail="%s; %s kept its last outputs. Build it: %s"
                              % (problem, sys.argv[1], BUILD))
        print("venv-step: %s; %s not run, its last outputs kept. Build it: %s" % (problem, sys.argv[1], BUILD))
        return 0
    pipeline_state.record(MARKER, "checked", detail="%s imports %s" % (py, NEEDS))
    script = os.path.join(ROOT, sys.argv[1])
    os.execv(py, [py, script] + sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
