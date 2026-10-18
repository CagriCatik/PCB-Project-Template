#!/bin/bash
# Firmware build/test: PROJECT --target host|stm32|arduino.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" firmware "$@"
