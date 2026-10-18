#!/bin/bash
# Plugin management: status | verify [NAME] | updates | guide NAME | install-ibom | install-archive.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ $# -eq 0 ]]; then set -- status; fi
exec "$HERE/kit" plugins "$@"
