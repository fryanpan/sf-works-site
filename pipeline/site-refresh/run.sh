#!/bin/bash
# What the daily timer runs on the VM: fetch origin, then run refresh.py in the analysis virtualenv so every step has
# numpy, shapely and pyproj. refresh.py brings the clone to origin/main itself (sync_to_main, which keeps output a
# stopped run left behind) and re-runs itself if main brought a newer version of it. The work is inside main() so
# bash has read all of it before anything rewrites this file.
main() {
  set -uo pipefail
  cd "$(dirname "$0")/../.." || exit 1
  export PATH="$HOME/.local/bin:$PATH" PYTHONHASHSEED=0 GIT_TERMINAL_PROMPT=0
  git fetch -q origin || echo "git fetch failed; running on the last fetched main"
  exec "${SF_WORKS_VENV:-$HOME/.venvs/sf-works-geo}/bin/python" pipeline/site-refresh/refresh.py "$@"
}
main "$@"
exit
