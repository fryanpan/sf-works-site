#!/bin/bash
# Install the 511 realtime archive on the cloud VM: the scripts in ~/rt-archive/bin (a copy, so the refresh clone's
# daily reset to main never changes them mid-poll), the virtualenv ~/.venvs/rt-archive, and the three systemd user
# timers (poll every minute, daily check and compaction, hourly freshness). It retires the old muni-511-collector
# system service first, because the archive polls Vehicle Positions too and both together would pass 511's 60 requests
# an hour, and copies that collector's snapshots (~/muni-511/raw, every 90 s from 2026-11-08) into the spool so the
# poller uploads them. Idempotent; rerun after changing anything here. Run it before infra/realtime-archive/attach-vm-sa.sh,
# which moves the VM onto the archive's service account; until then snapshots wait in the spool.
# Run on the VM from a clone: RT_ARCHIVE_BUCKET=<bucket> GCP_PROJECT=<project> bash tools/muni/rt-archive/vm-setup.sh
# The bucket and project are written to ~/.config/sf-works/env, which the systemd units read; they are not in the repo.
set -euo pipefail
S=$(cd "$(dirname "$0")" && pwd)
E=~/.config/sf-works/env
mkdir -p ~/.config/sf-works
touch "$E"
for k in RT_ARCHIVE_BUCKET GCP_PROJECT; do
  v="${!k:-}"
  if [ -n "$v" ]; then grep -v "^$k=" "$E" > "$E.tmp" || true; echo "$k=$v" >> "$E.tmp"; mv "$E.tmp" "$E"; fi
done
grep -q '^RT_ARCHIVE_BUCKET=.' "$E" || { echo "set RT_ARCHIVE_BUCKET (and GCP_PROJECT) for the first run" >&2; exit 1; }
V=~/.venvs/rt-archive
mkdir -p ~/rt-archive/bin ~/rt-archive/spool ~/rt-archive/state ~/rt-archive/parquet ~/.config/systemd/user
cp "$S"/*.py ~/rt-archive/bin/
[ -x $V/bin/python ] || python3 -m venv $V
$V/bin/pip install -q -r "$S/requirements.txt"

if systemctl is-enabled -q muni-511-collector 2>/dev/null || systemctl is-active -q muni-511-collector 2>/dev/null; then
  sudo systemctl disable --now muni-511-collector
fi
# The old collector's files, renamed onto the archive's layout. Their times are the collector's own fetch times.
if [ -d ~/muni-511/raw ] && [ ! -f ~/rt-archive/state/collector-imported ]; then
  for f in ~/muni-511/raw/*/*.pb.gz; do
    d=$(basename "$(dirname "$f")"); t=$(basename "$f" .pb.gz)
    dest=~/rt-archive/spool/sf/vehicle_positions/${d:0:4}/${d:5:2}/${d:8:2}/${t:0:2}/${d//-/}T${t}Z.pb.gz
    mkdir -p "$(dirname "$dest")"; [ -f "$dest" ] || cp -p "$f" "$dest"
  done
  touch ~/rt-archive/state/collector-imported
fi

# The daily check starts from here; the collector snapshots copied above are older and not held to the interval.
[ -f ~/rt-archive/state/started-at ] || date -u -d "+1 minute" +%Y-%m-%dT%H:%M:00+00:00 > ~/rt-archive/state/started-at
cp "$S"/rt-archive-*.service "$S"/rt-archive-*.timer ~/.config/systemd/user/
loginctl show-user "$USER" -p Linger | grep -q yes || sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now rt-archive-poll.timer rt-archive-daily.timer
# The hourly freshness check starts only once the VM writes as the archive's account (attach-vm-sa.sh starts it then);
# before that the bucket has nothing new, and it would alert every hour.
sa=$(curl -s -H Metadata-Flavor:Google http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email)
if [ "${sa%%@*}" = sf-rt-archive ]; then systemctl --user enable --now rt-archive-fresh.timer; else systemctl --user enable rt-archive-fresh.timer; systemctl --user stop rt-archive-fresh.timer; fi
systemctl --user list-timers 'rt-archive-*' --no-pager
