#!/bin/bash
# Compatibility alias for the one-time installation.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" install "$@"
