#!/bin/bash
# Move the scheduled site refresh on the cloud VM into this clone from another clone it runs in now (OLD), once.
# It copies OLD's refetchable caches here so the first run here is not a cold read of every source, installs the
# timer's units pointing at this clone (vm-setup.sh), and keeps any drop-in the service already has. OLD is left as it
# is, so the move can be undone (see the end of this file).
#
#   git clone https://github.com/fryanpan/sf-works-site.git ~/sf-works-site      # with git-lfs installed first
#   bash ~/sf-works-site/pipeline/site-refresh/move-refresh.sh ~/<old clone>             # check, then ask before moving
#   bash ~/sf-works-site/pipeline/site-refresh/move-refresh.sh ~/<old clone> --yes       # no question
#
# It stops before changing anything when: gh cannot push to this repo, a refresh is running, the last run's pull
# request is still recorded as open (its number belongs to OLD's repo), or ~/.config/sf-works/env lacks
# RT_ARCHIVE_BUCKET or GCP_PROJECT, which the Muni crowding step reads. Settings are described in lib/settings.py;
# this script never writes their values.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
OLD=$(cd "${1:?usage: move-refresh.sh <old clone> [--yes]}" && pwd)
YES=${2:-}
NEW=$(cd "$(dirname "$0")/../.." && pwd)
STATE=~/.local/state/sf-works-refresh
ENV=~/.config/sf-works/env
UNIT=~/.config/systemd/user/sf-works-refresh.service
die() { echo "move-refresh: $*" >&2; exit 1; }

[ "$OLD" != "$NEW" ] || die "OLD is this clone"
[ -f "$OLD/.git/HEAD" ] || [ -f "$OLD/.git" ] || die "$OLD is not a git clone"

# 1. Checks that change nothing.
command -v git-lfs >/dev/null || die "git-lfs is not installed: sudo apt-get install -y git-lfs, then git lfs pull here"
git -C "$NEW" lfs install --local >/dev/null
git -C "$NEW" lfs pull
if git -C "$NEW" lfs ls-files | grep -q ' - '; then die "some LFS files are still pointers; git lfs pull failed"; fi
gh auth status >/dev/null 2>&1 || die "gh is not logged in"
gh auth setup-git >/dev/null
# A dry-run push asks GitHub for write access over HTTPS and sends nothing.
git -C "$NEW" push --dry-run -q origin HEAD:refs/heads/move-refresh-write-check 2>/dev/null \
  || die "gh's token cannot push to $(git -C "$NEW" remote get-url origin); it needs this repo with contents, pull requests and issues read and write"
mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || die "a refresh is running; wait for it to finish"
[ ! -f "$STATE/pending.json" ] || die "the last run's pull request is recorded as open ($(cat "$STATE/pending.json")). \
Merge or close it in OLD's repo, then delete $STATE/pending.json"
touch "$ENV"
for k in RT_ARCHIVE_BUCKET GCP_PROJECT; do
  grep -q "^$k=." "$ENV" || die "$ENV has no $k= line; add it (lib/settings.py names each key)"
done
grep -q '^ALERT_REPO=.' "$ENV" || echo "move-refresh: ALERT_REPO is not set, so alerts and the heartbeat go to this repo's issues"

echo "move-refresh: the refresh moves from $OLD to $NEW"
if [ "$YES" != "--yes" ]; then
  read -r -p "Go ahead? [y/N] " ok
  [ "$ok" = y ] || die "nothing changed"
fi

# 2. The caches, at the same paths in both layouts, copied while this script holds the refresh's lock. Every one is
# gitignored here, so the copy adds no untracked file. Nothing outside this clone has changed yet.
for d in .cache data/socrata-cache data/store data/osm-cache data/pipeline-state data/dpw-cache data/sfmta-pages \
         data/dept-pages-cache data/bos-meetings/meetings data/audit/cache data/cgj/pdf data/school-hour-crashes/raw \
         out/street-work/cache out/permit-timing/cache out/north-star/cache out/growbikenet/work; do
  if [ -d "$OLD/$d" ]; then
    mkdir -p "$NEW/$d"
    rsync -a "$OLD/$d/" "$NEW/$d/"
    echo "copied $d ($(du -sh "$NEW/$d" | cut -f1))"
  fi
done
left=$(git -C "$NEW" status --porcelain)
[ -z "$left" ] || die "the copy left changed or untracked files here (is .gitignore current?); the timer still runs OLD:
$left"

# 3. Stop the timer, and keep the unit it runs now so the move can be undone.
systemctl --user stop sf-works-refresh.timer
[ ! -f "$UNIT" ] || cp "$UNIT" "$UNIT.before-move"

# 4. Install: Node, gh, the virtualenvs, the units naming this clone, linger, and the timer started again.
# The service's drop-ins in sf-works-refresh.service.d/ are left as they are.
exec 9>&-
bash "$NEW/pipeline/site-refresh/vm-setup.sh"

# 5. Show what the timer will run.
systemctl --user cat sf-works-refresh.service --no-pager | grep -E '^# /|^ExecStart|^WorkingDirectory|^Environment'
grep -q "$NEW/pipeline/site-refresh/run.sh" "$UNIT" || die "the unit does not run $NEW/pipeline/site-refresh/run.sh"
(cd "$NEW" && python3 pipeline/transportation-update.py --dry-run >/dev/null) || die "the pipeline cannot plan its steps here"
systemctl --user list-timers sf-works-refresh.timer --no-pager
echo "move-refresh: done. Start the first run now with: systemctl --user start --no-block sf-works-refresh.service"
echo "  and follow it in $STATE/logs/. It rebuilds every step once, because the change tracking records file paths."

# To undo, while OLD still holds its own refresh scripts:
#   systemctl --user stop sf-works-refresh.timer
#   mv ~/.config/systemd/user/sf-works-refresh.service.before-move ~/.config/systemd/user/sf-works-refresh.service
#   systemctl --user daemon-reload && systemctl --user start sf-works-refresh.timer
