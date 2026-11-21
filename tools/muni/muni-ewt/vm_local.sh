#!/bin/bash
# The Muni 511 step of the site's scheduled refresh, run on the VM itself (no gcloud): fetch any new month of 511
# historic stop observations (pull_all.py, through last month), rebuild only the months whose inputs or scripts changed
# (rerun_all.py), summarise (post_all.sh), then copy the small outputs into data/muni-ewt/ of this repo, the same set
# vm_sync.sh pull brings back. Change marker: a month directory gains DONE only when 511 has posted it and it was
# extracted; a run with no new month rebuilds nothing and copies identical files. A failed rebuild or summary exits
# non-zero before anything is copied, so the last good data/muni-ewt/ stays. A month 511 hasn't posted, or a failed
# fetch, is logged by pull_all.py and left for the next run; the muni/newest-month check fails once the newest month is
# over 40 days old. pull_all.py runs without the orchestrator's NET_LOG, whose request log would hold the token in the
# 511 URL. Not on the VM (no ~/muni-511): says so and exits 0,
# so the page builds still run on the copy in the repo. The 511 token stays in ~/.511token and is never read here.
# Usage: tools/muni/muni-ewt/vm_local.sh [ewt dir, default ewt]
set -euo pipefail
# R is the repo root, the nearest folder above this script that holds lib/paths.py.
R=$(cd "$(dirname "$0")" && while [ ! -f lib/paths.py ] && [ "$PWD" != / ]; do cd ..; done && pwd); H=$HOME/muni-511; E=${1:-ewt}; S=$(cd "$(dirname "$0")" && pwd)
if [ ! -d "$H/history" ]; then echo "muni-511: not on the VM ($H missing); last good data/muni-ewt kept" >&2; exit 0; fi
last=$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)
cd "$H"
env -u NET_LOG nice -n 10 python3 "$S/pull_all.py" 2022-01 "$last"
nice -n 10 python3 "$S/rerun_all.py" "$E"
bash "$S/post_all.sh" "$E"
T=$(mktemp -d)
# the date each month's stop observations were read: its DONE marker's date (pull_all.py writes it once the month is
# fetched and extracted), so the optimizer's "Data updated" line is the date the data was read (pre-send R5-13)
(echo "month,read"; for d in history/regional-*-so-sf; do if [ -f "$d/DONE" ]; then m=${d#history/regional-}; echo "${m%-so-sf},$(date -u -r "$d/DONE" +%F)"; fi; done | sort) > "$T/read_511.csv"
cd "$H/$E"
tar cf - extract.csv extract_months.csv extract_freq.csv summary diag feed_quality.txt summary_{cov95,eb,noguard}/system_{year,month}.csv \
  summary_trip seg/*.json ref/route_types.csv stops stophours daily ontime/*-stops.csv ontime/*-lines.csv ontime/*-check.json | tar xf - -C "$T"
# the by-hour and 6-hour files cover the newest three months only: clear the old ones so a month that rolled off goes
rm -f "$R"/data/muni-ewt/daily/hourly-*.csv "$R"/data/muni-ewt/daily/6h-*.csv
cp -R "$T"/. "$R/data/muni-ewt/"
rm -r "$T"
echo "muni-511: data/muni-ewt refreshed through $(tail -1 extract_months.csv | cut -d, -f1)"
