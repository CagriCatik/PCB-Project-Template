#!/bin/bash
# Interactive PCB project manager. Double-click in Finder or run from Terminal.
# Non-interactive equivalent for automation: scripts/kit <command> (see --help).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
STATUS=0
"$HERE/scripts/kit" manager || STATUS=$?
if [[ -t 0 ]]; then
  printf '\nPress Enter to close... '
  IFS= read -r _ || true
fi
exit "$STATUS"
