#!/bin/bash
# Read-only environment diagnostics.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" doctor "$@"
