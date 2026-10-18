#!/bin/bash
HERE="$(cd "$(dirname "$0")/.." && pwd -P)"
exec "$HERE/scripts/kit" gui "$@"
