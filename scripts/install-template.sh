#!/bin/bash
# One-time environment installation (same as install_template.command).
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" install "$@"
