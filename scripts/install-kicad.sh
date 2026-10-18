#!/bin/bash
# Install the official macOS app bundle without replacing an existing installation.
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: install-kicad.sh [--dmg FILE | --url HTTPS_URL --sha256 HASH] [--dest DIRECTORY]
Install exactly KiCad 10.0.7 on macOS. Default destination: /Applications/KiCad.
Download the universal 10.0.7 DMG from https://www.kicad.org/download/macos/.
A URL download requires its published SHA-256. Local DMGs may also use --sha256.
Existing 10.0.7 installations are left alone; other installations are never overwritten.
Use --dest "$HOME/Applications/KiCad" for an installation without administrator access.
HELP
}
fail() { echo "Error: $*" >&2; exit 1; }
dmg='' url='' checksum='' dest='/Applications/KiCad'
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dmg|--url|--sha256|--dest)
      (($# >= 2)) || fail "Missing value for $1"
      case "$1" in
        --dmg) dmg=$2 ;; --url) url=$2 ;; --sha256) checksum=$2 ;; --dest) dest=$2 ;;
      esac
      shift 2 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done
[[ $(uname -s) == Darwin ]] || fail 'This installer supports macOS only.'
[[ "$dest" == /* && "$dest" != / ]] || fail '--dest must be an absolute directory path other than /.'
cli="$dest/KiCad.app/Contents/MacOS/kicad-cli"
if [[ -e "$dest" || -L "$dest" ]]; then
  if [[ -x "$cli" && "$("$cli" version)" == 10.0.7 ]]; then
    echo "KiCad 10.0.7 is already installed at $dest"; exit 0
  fi
  fail "Destination already exists: $dest. Choose a new --dest or move it manually."
fi
[[ -z "$dmg" || -z "$url" ]] || fail 'Choose --dmg or --url, not both.'
[[ -n "$dmg$url" ]] || { usage; exit 1; }
if [[ -n "$checksum" ]]; then
  [[ "$checksum" =~ ^[[:xdigit:]]{64}$ ]] || fail 'SHA-256 must contain 64 hexadecimal characters.'
  checksum=$(printf '%s' "$checksum" | tr '[:upper:]' '[:lower:]')
fi
work=$(mktemp -d)
mounted=0
stage=''
cleanup() {
  if [[ $mounted == 1 ]]; then hdiutil detach "$work/mount" -quiet || true; fi
  [[ -z "$stage" ]] || rm -rf -- "$stage"
  rm -rf -- "$work"
}
trap cleanup EXIT
if [[ -n "$url" ]]; then
  [[ "$url" == https://* && -n "$checksum" ]] || fail 'URL downloads require HTTPS and --sha256.'
  dmg="$work/kicad.dmg"
  curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 --output "$dmg" "$url"
fi
[[ -f "$dmg" ]] || fail "DMG does not exist: $dmg"
if [[ -n "$checksum" ]]; then
  actual=$(shasum -a 256 "$dmg"); actual=${actual%% *}
  [[ "$actual" == "$checksum" ]] || fail 'DMG SHA-256 mismatch.'
fi
hdiutil verify "$dmg"
mkdir "$work/mount"
hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$work/mount" -quiet
mounted=1
source_app=$(find "$work/mount" -name KiCad.app -type d -prune -print | head -n 1)
[[ -n "$source_app" ]] || fail 'KiCad.app was not found in the image.'
codesign --verify --deep --strict "$source_app"
spctl --assess --type execute "$source_app"
[[ "$("$source_app/Contents/MacOS/kicad-cli" version)" == 10.0.7 ]] || fail 'The DMG does not contain KiCad 10.0.7.'
parent=$(dirname "$dest")
mkdir -p "$parent"
[[ -w "$parent" ]] || fail "Destination parent is not writable. Use --dest \"\$HOME/Applications/KiCad\"."
stage=$(mktemp -d "$parent/.kicad-install.XXXXXX")
# The official disk image ships the main app and companion app bundles together.
for app in "$(dirname "$source_app")/"*.app; do
  [[ -d "$app" ]] || continue
  ditto "$app" "$stage/$(basename "$app")"
done
[[ "$("$stage/KiCad.app/Contents/MacOS/kicad-cli" version)" == 10.0.7 ]] || fail 'Copied installation failed version verification.'
[[ ! -e "$dest" && ! -L "$dest" ]] || fail 'Destination appeared during installation; refusing to overwrite.'
mv "$stage" "$dest"
stage=''
echo "Installed KiCad 10.0.7 at $dest"
echo "CLI: $dest/KiCad.app/Contents/MacOS/kicad-cli"
