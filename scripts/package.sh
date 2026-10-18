#!/bin/bash
# Source ZIP of the kit: --output FILE (outside the repository).
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" package "$@"
