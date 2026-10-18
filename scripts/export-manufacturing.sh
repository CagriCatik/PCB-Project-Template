#!/bin/bash
# Manufacturing exports: PROJECT --revision REV [--approval FILE --authorize].
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" export "$@"
