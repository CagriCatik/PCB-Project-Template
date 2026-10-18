#!/bin/bash
# One-time, idempotent environment installation. Double-click in Finder or run
# from Terminal; options are passed through (see: scripts/kit install --help).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
STATUS=0
"$HERE/scripts/kit" install "$@" || STATUS=$?
if [[ -t 0 && "$#" -eq 0 ]]; then
  printf '\nPress Enter to close... '
  IFS= read -r _ || true
fi
exit "$STATUS"
