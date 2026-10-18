#!/bin/bash
# Thermal estimate: analyze PROJECT [--power REF=W] [--ambient C] [--grid MM] | compare RUN_A RUN_B.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" thermal "$@"
