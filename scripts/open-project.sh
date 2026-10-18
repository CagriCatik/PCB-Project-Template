#!/bin/bash
# Open PROJECT in KiCad (default) or with --vscode.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" open "$@"
