#!/bin/bash
# Install VS Code extensions useful for PCB-Project-Template and its generated projects.
#
# Usage: scripts/install-vscode-extensions.sh [--optional] [--no-firmware] [--update] [--dry-run] [--list]
#   (default)      core + firmware groups
#   --optional     also install the optional group (heavier or niche extensions)
#   --no-firmware  skip the firmware group (PCB-only work)
#   --update       reinstall already installed extensions to get the latest version
#   --dry-run      show what would be installed, change nothing
#   --list         print the extension groups and exit
#
# Extensions are downloaded from the Visual Studio Marketplace by VS Code's own
# CLI (`code --install-extension`). Already installed extensions are skipped,
# so the script is safe to re-run. All IDs were checked against the
# Marketplace on 2026-10-18.
set -euo pipefail

CORE=(
  "ms-python.python                       Python: tools/, tests, fixture builders"
  "ms-python.vscode-pylance               Python language server (types, navigation)"
  "charliermarsh.ruff                     Python linting/formatting"
  "mechatroner.rainbow-csv                pinmap.csv, power_budget.csv, BOM and position files"
  "yzhang.markdown-all-in-one             docs/, checklists, tables of contents"
  "davidanson.vscode-markdownlint         Markdown consistency for docs/"
  "timonwong.shellcheck                   Lint for scripts/*.sh and *.command"
  "tomoki1207.pdf                         Datasheets, schematic.pdf, assembly drawings"
  "ms-vscode.live-server                  Preview thermal_report.html and Interactive HTML BOM"
  "mhutchie.git-graph                     Review history before you commit"
  "streetsidesoftware.code-spell-checker  Spell checking for docs and comments"
)
FIRMWARE=(
  "ms-vscode.cpptools                     C/C++ IntelliSense for firmware/"
  "ms-vscode.cmake-tools                  CMake presets: host-tests, stm32-debug"
  "marus25.cortex-debug                   Debug STM32 via OpenOCD / ST-LINK / J-Link"
  "dan-c-underwood.arm                    Syntax for CubeMX startup_*.s files"
  "zixuanwang.linkerscript                Syntax for STM32 *.ld linker scripts"
  "ms-vscode.hexeditor                    Inspect .bin/.hex/.elf outputs"
)
OPTIONAL=(
  "platformio.platformio-ide              Arduino Shield firmware (installs PlatformIO Core itself)"
  "stmicroelectronics.stm32-vscode-extension  ST's STM32 workflow (expects STM32CubeCLT)"
  "eamodio.gitlens                        Extended Git blame/history"
  "foxundermoon.shell-format              Shell script formatting"
  "streetsidesoftware.code-spell-checker-german  German dictionary (README is German)"
  "DanielMeza.kicad-syntax-highlighter    KiCad file syntax highlighting (small user base)"
  "argmaster.gerber-x3-x2-format-support  Gerber X2/X3 syntax (small user base)"
)

optional=0 firmware=1 update=0 dry=0
for arg in "$@"; do
  case "$arg" in
    --optional) optional=1 ;;
    --no-firmware) firmware=0 ;;
    --update) update=1 ;;
    --dry-run) dry=1 ;;
    --list)
      for group in CORE FIRMWARE OPTIONAL; do
        echo "[$group]"; eval 'printf "  %s\n" "${'"$group"'[@]}"'
      done
      exit 0 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

# Locate the VS Code CLI without requiring "Shell Command: Install 'code' in PATH".
CODE=""
for candidate in "$(command -v code 2>/dev/null || true)" \
    "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
    "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then CODE="$candidate"; break; fi
done
if [[ -z "$CODE" ]]; then
  echo "VS Code CLI not found. Install VS Code from https://code.visualstudio.com/ or run" >&2
  echo "'Shell Command: Install code command in PATH' from the VS Code command palette." >&2
  exit 1
fi

selected=("${CORE[@]}")
[[ $firmware == 1 ]] && selected+=("${FIRMWARE[@]}")
[[ $optional == 1 ]] && selected+=("${OPTIONAL[@]}")

installed="$("$CODE" --list-extensions 2>/dev/null | tr '[:upper:]' '[:lower:]')"
done_count=0 skipped=0 failed=()
echo "VS Code CLI: $CODE"
for entry in "${selected[@]}"; do
  id="${entry%% *}"
  purpose="$(echo "${entry#"$id"}" | sed 's/^ *//')"
  lower="$(echo "$id" | tr '[:upper:]' '[:lower:]')"
  if grep -qx "$lower" <<<"$installed" && [[ $update == 0 ]]; then
    printf '  = %-45s already installed\n' "$id"; skipped=$((skipped + 1)); continue
  fi
  if [[ $dry == 1 ]]; then
    printf '  + %-45s would install (%s)\n' "$id" "$purpose"; continue
  fi
  printf '  + %-45s %s\n' "$id" "$purpose"
  args=(--install-extension "$id")
  [[ $update == 1 ]] && args+=(--force)
  if "$CODE" "${args[@]}" >/dev/null 2>&1; then
    done_count=$((done_count + 1))
  else
    failed+=("$id")
  fi
done

echo "Installed/updated: $done_count, already present: $skipped, failed: ${#failed[@]}"
if (( ${#failed[@]} )); then
  printf 'Failed: %s\n' "${failed[@]}" >&2
  echo "Check the network connection and run again; already installed extensions are skipped." >&2
  exit 1
fi
