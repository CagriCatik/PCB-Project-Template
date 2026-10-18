#!/bin/bash
# Create an independent project: --template ID --name NAME --dest DIR.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" create "$@"
