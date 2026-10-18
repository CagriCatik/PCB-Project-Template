#!/bin/bash
# Backward-compatible read-only verification entrypoint.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec "$ROOT/scripts/verify.sh" "$@"
