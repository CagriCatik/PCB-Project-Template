#!/bin/bash
# Quality gates for PROJECT (ERC, DRC, parity, libraries, metadata, 3D, BOM).
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" verify "$@"
