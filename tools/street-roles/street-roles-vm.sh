#!/usr/bin/env bash
# Runs the Street Roles Map's route stage (tools/street-roles/street-roles.py route: every commute pair's shortest path, and the connected counts today and with the network) on a GCP VM, then copies its two outputs back.
#
# Usage: tools/street-roles/street-roles-vm.sh
# The VM's name is the ROUTE_VM setting (environment or local-settings.json, lib/settings.py), and its zone
# ROUTE_VM_ZONE. Needs gcloud signed in to the project that holds the VM. The VM is started if it is stopped
# and left running (other jobs share it). prepare runs on the laptop first, since it only reads held copies.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
setting() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from lib import settings; print(settings.get(sys.argv[2]) or "")' "$REPO" "$1"; }
VM=$(setting ROUTE_VM)
ZONE=$(setting ROUTE_VM_ZONE)
[ -n "$VM" ] && [ -n "$ZONE" ] || { echo "street-roles-vm: set ROUTE_VM and ROUTE_VM_ZONE (see lib/settings.py)" >&2; exit 1; }
DIR=street-roles-run
ssh_vm() { gcloud compute ssh "$VM" --zone "$ZONE" --command "$1"; }

status=$(gcloud compute instances describe "$VM" --zone "$ZONE" --format="value(status)")
if [ "$status" != "RUNNING" ]; then
  gcloud compute instances start "$VM" --zone "$ZONE"
  for _ in $(seq 1 30); do ssh_vm true 2>/dev/null && break; sleep 10; done
fi
tmp=$(mktemp -d)
tar -czf "$tmp/sr.tgz" -C "$REPO" tools/street-roles/street-roles.py lib/__init__.py lib/paths.py lib/stable.py \
  site/data/street-roles/streets.json site/data/street-roles/commutes.json
gcloud compute scp --zone "$ZONE" "$tmp/sr.tgz" "$VM":~/sr.tgz
ssh_vm "set -e; rm -rf $DIR; mkdir -p $DIR && tar -xzf sr.tgz -C $DIR && cd $DIR && PYTHONHASHSEED=0 python3 tools/street-roles/street-roles.py route > route.log 2>&1 || { tail -20 route.log; exit 1; }; tail -5 route.log"
gcloud compute scp --zone "$ZONE" "$VM":~/$DIR/site/data/street-roles/commutes.json "$REPO/site/data/street-roles/commutes.json"
mkdir -p "$REPO/out/street-roles"
gcloud compute scp --zone "$ZONE" "$VM":~/$DIR/out/street-roles/summary.json "$REPO/out/street-roles/summary.json"
rm -rf "$tmp"
python3 "$REPO/tools/street-roles/street-roles.py" check
