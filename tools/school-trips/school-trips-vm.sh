#!/bin/bash
# School Trips' bikeway program, simulation and every output downstream of them, on a sim VM booted from a disk snapshot that holds the untracked inputs.
#
#   sim-vm.py run --commit <sha on main> --snapshot <sim snapshot> \
#       --inputs-root <inputs checkout> \
#       --input data/osm-cache --input data/socrata-cache --input .cache/muni-gtfs --input .cache/street-grades \
#       --expect-inputs <manifest> --inputs-manifest out/school-trips-vm/inputs.json \
#       --cmd "bash tools/school-trips/school-trips-vm.sh" --time-limit 86400 \
#       --out out/school-sim --out out/school-kids-hurt --out out/school-trips-vm --out site/data --out data/school-sim
#
# The steps are the ones PR #283 ran by hand on a sim VM: segments, sim, overlays, the sim's checks, then the
# light steps that read them (grounds, calm order, rules, speed levers, kids hurt, crossings, injury points and map,
# hurt maps, trip graph), the budget plans with their exact check split over 12 processes, figures and the trip check.
#
# INPUTS. The OSM, crash, GTFS and DEM caches come from the snapshot, and sim-vm.py's agent hashes them against
# --expect-inputs before this runs; the script stops unless out/school-trips-vm/inputs.json says they matched.
# PRECHECK. Then every light step runs once on the commit's own outputs and must reproduce them (data/,
# out/ and site/data/, inputs and pipeline-state aside), so crash or school data that differs from what the committed
# outputs were built from stops the job in minutes, not after the program. GTFS and DEM tiles feed only the sim, so
# the manifest is their check. The calm order must come out unchanged after the sim: the bikeway program does not
# move it. The python virtualenv is the snapshot's (PY).
#
# SEGMENTS_ROUNDS defaults to the script's own 4; the other segments settings are #283's. Logs, the step times
# and the promise-against-check table (gaps.log) land in out/school-trips-vm/.
set -uo pipefail
cd "$(dirname "$0")" && while [ ! -f lib/paths.py ] && [ "$PWD" != / ]; do cd ..; done  # the repo root
PY=${PY:-$HOME/.venvs/sf-works-geo/bin/python}
L=out/school-trips-vm; mkdir -p $L
# Node 24.14.0, the version #283's plans ran on. The sim snapshot has none, so it is fetched from nodejs.org
# and must match the release's published SHA-256 (SHASUMS256.txt for v24.14.0).
NODE_V=v24.14.0 NODE_SHA=41cd79bb7877c81605a9e68ec4c91547774f46a40c67a17e34d7179ef11729df
NODE_BIN=${NODE_BIN:-/var/simjob/deps/node-$NODE_V-linux-x64/bin}
if [ ! -x "$NODE_BIN/node" ]; then
  mkdir -p /var/simjob/deps && curl -fsSL --connect-timeout 30 --max-time 600 --retry 3 -o /var/simjob/deps/node.tar.xz \
    "https://nodejs.org/dist/$NODE_V/node-$NODE_V-linux-x64.tar.xz" \
    && echo "$NODE_SHA  /var/simjob/deps/node.tar.xz" | sha256sum -c - >> $L/steps.log \
    && tar -xJf /var/simjob/deps/node.tar.xz -C /var/simjob/deps \
    || { echo "STOPPED: could not fetch node $NODE_V with the pinned SHA-256" >> $L/steps.log; exit 7; }
fi
[ -x "$NODE_BIN/node" ] || { echo "STOPPED: no node at $NODE_BIN" >> $L/steps.log; exit 7; }
export PATH=$NODE_BIN:$PATH PYTHONHASHSEED=0 PYTHONUNBUFFERED=1 SF_WORKS_VENV=$(dirname "$(dirname "$PY")")
echo "== node $(node --version), python $($PY --version 2>&1)" >> $L/steps.log
# Worker counts are #283's on a 32-CPU VM, capped at this VM's CPUs.
NP=$(nproc); SEGW=$(( NP > 16 ? 14 : NP - 2 )); SIMW=$(( NP < 30 ? NP : 30 ))
SEG=(SEGMENTS_THREADS=8 SEGMENTS_SOLVE_WORKERS=8 SEGMENTS_CPSAT_MEM_MB=60000 SEGMENTS_RUN_CAP_MB=80000
     SEGMENTS_TIME_LIMIT=300 SCHOOL_SIM_MAX_WORKERS=$SEGW)
# A resumed run may set the solver, the round, per-round time limits, the program's cover share and the memory caps,
# e.g. SEGMENTS_RESUME="4:<segments-round-*.npz>" SEGMENTS_SOLVER=highs SEGMENTS_TIME_LIMIT=300,300,300,3600; each one
# given replaces #283's.
for v in SEGMENTS_ROUNDS SEGMENTS_SOLVER SEGMENTS_RESUME SEGMENTS_TIME_LIMIT SEGMENTS_PROG_MIN_SHARE \
         SEGMENTS_CPSAT_MEM_MB SEGMENTS_RUN_CAP_MB; do
  [ -n "${!v:-}" ] && SEG+=("$v=${!v}")
done
echo "== segments settings: ${SEG[*]}; segments workers $SEGW, sim workers $SIMW" >> $L/steps.log

step() {  # step <name> <command...>: log to $L/<name>.log, time it in steps.log, stop the job on failure
  local name=$1; shift
  echo "== $name start $(date -u +%FT%TZ)" >> $L/steps.log
  "$@" > $L/$name.log 2>&1; local rc=$?
  echo "== $name exit $rc $(date -u +%FT%TZ)" >> $L/steps.log
  [ $rc -eq 0 ] || { echo "STOPPED at $name (exit $rc)" >> $L/steps.log; exit $rc; }
}
light() {  # every light step, in #283's order; $1 prefixes the log names
  step $1grounds nice -n 15 $PY tools/school-trips/school-grounds.py
  step $1calmpri nice -n 15 $PY tools/school-trips/school-calm-priority.py
  step $1rules nice -n 15 $PY tools/school-trips/school-sim-rules.py
  step $1speed nice -n 15 $PY tools/school-trips/school-speed-levers.py
  step $1kidshurt nice -n 15 $PY tools/school-trips/school-kids-hurt.py
  step $1injpts nice -n 15 $PY tools/school-trips/school-injury-points.py
  step $1injmap nice -n 15 $PY tools/street-safety/injury-map.py
  step $1hurtmaps nice -n 15 $PY tools/school-trips/school-hurt-maps.py
  step $1tripgraph nice -n 15 $PY tools/school-trips/school-trip-graph.py
}
snap() { rm -rf "$1"; mkdir -p "$1"; tar -cf - --exclude data/osm-cache --exclude data/socrata-cache \
  --exclude data/pipeline-state --exclude $L data out site/data | tar -xf - -C "$1"; }

PIDS=()
# On any exit, stop the exact-check parts still running, so nothing writes while the agent packs the result.
trap 'if [ ${#PIDS[@]} -gt 0 ]; then kill "${PIDS[@]}" 2>/dev/null; fi' EXIT
$PY -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("expected") is True else 1)' $L/inputs.json \
  || { echo "STOPPED: no matched input manifest at $L/inputs.json (pass --expect-inputs)" >> $L/steps.log; exit 6; }
echo "== inputs match the expected manifest" >> $L/steps.log
BASE=/tmp/school-trips-base
snap $BASE
light pre-
snap /tmp/school-trips-pre
# Run-date stamps and last-digit float rounding (a Mac build against a Linux one) are allowed, and listed.
if ! $PY lib/tree_same.py $BASE /tmp/school-trips-pre > $L/precheck.txt 2>&1; then
  echo "PRECHECK FAILED: the light steps do not reproduce the commit's outputs on these inputs" >> $L/steps.log
  exit 4
fi
echo "== precheck passed: light steps reproduce the commit's outputs" >> $L/steps.log
cp data/school-sim/calm-priority.json /tmp/calm-before.json

step segments env "${SEG[@]}" nice -n 15 $PY tools/school-trips/school-sim.py --segments --workers $SEGW
# GAPS_STRICT=1 stops the job here unless every budget's promise and check agree within 2% for car trips and drivers
# and no solve in the last round kept its start (a solver that found nothing better within its time limit).
gaps() { GAPS_STRICT=${GAPS_STRICT:-0} $PY - <<'EOF'
import json, os, re, sys
d = json.load(open("out/school-sim/segments.json"))
bad = []
print("maxRounds", d["objective"]["maxRounds"])
print("%6s %9s %9s %7s %9s %9s %7s" % ("budget", "carProm", "carCheck", "gap%", "drvProm", "drvCheck", "gap%"))
for b in d["budgets"]:
    p = b["promise"]
    g = lambda a, c: 100 * abs(c - a) / max(a, c)
    print("%5sM %9.2f %9.2f %7.2f %9.1f %9.1f %7.2f" % (b["budgetM"], p["carTrips"], b["carTripsRemoved"],
          g(p["carTrips"], b["carTripsRemoved"]), p["drivers"], b["drivers"], g(p["drivers"], b["drivers"])))
    for k, a, c in (("car trips", p["carTrips"], b["carTripsRemoved"]), ("drivers", p["drivers"], b["drivers"])):
        if g(a, c) >= 2.0:
            bad.append("$%sM %s %.2f%% apart" % (b["budgetM"], k, g(a, c)))
last = d["objective"]["maxRounds"]
for line in open("out/school-trips-vm/segments.log"):
    if re.match(r"\s*round %d \$\d+M: \d+ chunks built" % last, line) and re.search(r"start kept|no solution", line, re.I):
        bad.append("kept start: " + line.strip()[:160])
print("\n".join("NOT MET: " + x for x in bad) or "all gaps under 2%, no kept start")
sys.exit(1 if bad and os.environ["GAPS_STRICT"] == "1" else 0)
EOF
}
step gaps gaps   # the table lands in gaps.log
step sim env SCHOOL_SIM_MAX_WORKERS=$SIMW nice -n 15 $PY tools/school-trips/school-sim.py --workers $SIMW
step overlays env SCHOOL_SIM_MAX_WORKERS=$SIMW nice -n 15 $PY tools/school-trips/school-sim.py --overlays --workers $SIMW
step check nice -n 15 $PY tools/school-trips/school-sim.py --check
light ""
cmp -s data/school-sim/calm-priority.json /tmp/calm-before.json || {
  echo "STOPPED: the calm order moved after the sim" >> $L/steps.log; exit 3; }

# The plans' exact check, split over 12 processes (PLANS_EXACT_KEYS); every part must finish before the merge reads them.
D=/tmp/school-trips-exact; rm -rf $D; mkdir -p $D; FROM=""
echo "== plans start $(date -u +%FT%TZ)" >> $L/steps.log
for b in 5 10 20 40 80 100; do for g in car safety; do k=$g$b; FROM="$FROM,$D/$k.json"
  PLANS_EXACT_KEYS=$k PLANS_EXACT_DUMP=$D/$k.json nice -n 15 node tools/school-trips/school-budget-plans.mjs > $L/exact-$k.log 2>&1 &
  PIDS+=($!)
done; done
# wait -n returns as each part ends, so the first failure stops the job at once; the EXIT trap stops the rest.
for _ in "${PIDS[@]}"; do wait -n || { echo "STOPPED: an exact-check part failed (exact-*.log)" >> $L/steps.log; exit 5; }; done
PIDS=()
step plans env PLANS_EXACT_FROM=${FROM#,} nice -n 15 node tools/school-trips/school-budget-plans.mjs
step figures nice -n 15 node tools/school-trips/school-trips-figures.mjs
step tripcheck nice -n 15 node tools/school-trips/school-trip-check.mjs
echo "ALL DONE $(date -u +%FT%TZ)" >> $L/steps.log
