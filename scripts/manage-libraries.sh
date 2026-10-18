#!/bin/bash
# Library tables: check [PROJECT] | register PROJECT --kind --name --source.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" libraries "$@"
