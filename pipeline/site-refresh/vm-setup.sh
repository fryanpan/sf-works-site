#!/bin/bash
# Set up the cloud VM to run the scheduled site refresh: Node 22 and gh in ~/.local, the analysis virtualenv
# ~/.venvs/sf-works-geo from pipeline/requirements-geo.txt and pipeline/requirements-refresh.txt, the Legistar scraper's
# virtualenv the Board of Supervisors mirror reads with, the timer units, and linger so the timer runs with nobody
# logged in. Idempotent; run on the VM from the refresh clone: bash pipeline/site-refresh/vm-setup.sh
# Settings that name private infrastructure go in ~/.config/sf-works/env (KEY=value lines, see lib/settings.py), which
# the timer's service reads; this script never writes them.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p ~/.local/bin ~/.local/opt ~/.config/sf-works
touch ~/.config/sf-works/env
# The newest Node 22 and the newest gh release, read off their publishers' own indexes.
NODE_V=$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt | grep -oE 'node-v22[.0-9]+-linux-x64.tar.xz' | head -1 | sed -E 's/node-(v[.0-9]+)-.*/\1/')
GH_V=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/cli/cli/releases/latest | sed -E 's#.*/v##')
if ! ~/.local/bin/node --version 2>/dev/null | grep -q "^v22"; then
  curl -fsSL https://nodejs.org/dist/$NODE_V/node-$NODE_V-linux-x64.tar.xz | tar xJ -C ~/.local/opt
  for b in node npm npx; do ln -sf ~/.local/opt/node-$NODE_V-linux-x64/bin/$b ~/.local/bin/$b; done
fi
if ! [ -x ~/.local/bin/gh ]; then
  curl -fsSL https://github.com/cli/cli/releases/download/v$GH_V/gh_${GH_V}_linux_amd64.tar.gz | tar xz -C ~/.local/opt
  ln -sf ~/.local/opt/gh_${GH_V}_linux_amd64/bin/gh ~/.local/bin/gh
fi
V=~/.venvs/sf-works-geo
# poppler-utils: pdftotext, pdfinfo and pdftoppm, which the meeting mirrors and their checks read minutes with.
for pkg in python3.12-venv poppler-utils git-lfs; do dpkg -s $pkg >/dev/null 2>&1 || sudo apt-get install -y -q $pkg; done
git -C "$R" lfs install --local >/dev/null
[ -x $V/bin/python ] || python3.12 -m venv $V
$V/bin/pip install -q -r "$R/pipeline/requirements-geo.txt" -r "$R/pipeline/requirements-refresh.txt"
# The community Legistar scraper (opencivicdata/python-legistar-scraper) that tools/meetings/fetch-bos-meetings.py
# imports, cloned with its own virtualenv under ~/.cache/sf-legistar (CACHE moves it), where that script looks.
L=${CACHE:-$HOME/.cache/sf-legistar}
[ -d "$L/python-legistar-scraper/.git" ] || { mkdir -p "$L" && git clone -q --depth 1 https://github.com/opencivicdata/python-legistar-scraper "$L/python-legistar-scraper"; }
[ -x "$L/venv/bin/python" ] || python3 -m venv "$L/venv"
"$L/venv/bin/python" -c 'import legistar.bills' 2>/dev/null || "$L/venv/bin/pip" -q install "$L/python-legistar-scraper"
# SFMTA's September 2022 GTFS capture, which the Muni dashboard build (tools/muni/muni-ewt/site_data.py) and
# retired_lines.py read to place stops and lines since retired. It is no longer downloadable, so it is copied from
# MUNI_GTFS_2022 when that names a copy on this machine.
if [ -n "${MUNI_GTFS_2022:-}" ] && [ -f "$MUNI_GTFS_2022" ] && ! cmp -s "$MUNI_GTFS_2022" "$R/.cache/muni-gtfs/hist/20220926.zip"; then
  mkdir -p "$R/.cache/muni-gtfs/hist" && cp "$MUNI_GTFS_2022" "$R/.cache/muni-gtfs/hist/20220926.zip"
fi
mkdir -p ~/.config/systemd/user
# The unit names the clone it runs in: this one.
sed "s#%h/sf-works-site#$R#g" "$R/pipeline/site-refresh/sf-works-refresh.service" > ~/.config/systemd/user/sf-works-refresh.service
cp "$R/pipeline/site-refresh/sf-works-refresh.timer" ~/.config/systemd/user/
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now sf-works-refresh.timer
systemctl --user list-timers sf-works-refresh.timer --no-pager
