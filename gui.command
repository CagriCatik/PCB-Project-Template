#!/bin/bash
# Desktop GUI launcher for PCB-Project-Template. Double-click in Finder or run from Terminal.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
STATUS=0
"$HERE/scripts/kit" gui "$@" || STATUS=$?
if [[ "$STATUS" -ne 0 && -t 0 ]]; then
  printf '\nProcess exited with error (%d). Press Enter to close... ' "$STATUS"
  IFS= read -r _ || true
fi
exit "$STATUS"
