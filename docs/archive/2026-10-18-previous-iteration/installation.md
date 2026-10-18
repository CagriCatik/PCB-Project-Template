# Installation and scope

The repository root is the reusable native KiCad template. Preserve its domain
folders. Installation copies source into a user-selected template parent as
`embedded-hw-fw/`. It does not move or restructure the repository.

The `.command` entrypoint remains executable and double-clickable on macOS.
It prompts for the parent directory; pressing Enter uses
`KICAD_USER_TEMPLATE_DIR` or `~/Documents/KiCad/templates`. Python 3.10+ must be
installed and available as `python3` (macOS does not always provide it). In a
terminal, pass `--parent PATH` for noninteractive installation. `~` expands.

Repeated identical installation verifies previously installed source hashes and
returns the same directory, leaving added user files untouched. Changed source,
modified installed files, or an unrelated existing destination stop the operation
without merging. Choose a new parent to keep both versions. No update removes
old user data. Installation stages files next to the destination before rename.

KiCad 10: File > New Project > Browse to the selected template parent > select
`embedded-hw-fw` (title **Embedded HW + FW**). The GUI intentionally excludes
`meta/` from generated projects. It generates blank root native files. Scripts,
agent instructions, hidden Git policies and domain directories are copied.

`./scripts/configure-kicad.sh PARENT` writes an environment snippet in the global
companion directory and prints the value to enter in Preferences > Configure
Paths. It does not edit application-owned preference JSON or silently change
running KiCad. Source the snippet before launching KiCad from the same terminal,
or set the path in KiCad's UI for persistent GUI launches.

## KiCad application

Use the official [macOS download](https://www.kicad.org/download/macos/).
`./scripts/install-kicad.sh --dmg /absolute/path/to/10.0.7.dmg` verifies the DMG,
application signature, Gatekeeper assessment and exact CLI version. For a URL,
use `--url HTTPS_URL --sha256 PUBLISHED_SHA256`. The installer never guesses a
mirror or replaces another app version. `--dest "$HOME/Applications/KiCad"`
avoids administrator writes. Existing 10.0.7 installs are reused. No DMG was
redownloaded or app replaced during this implementation.

## Global companion

Only optional IPC diagnostics require Python packages:

```sh
./scripts/install-environment.sh
export KICAD_KIT_PYTHON="$HOME/Library/Application Support/PCB-Project-Template/venv/bin/python"
./scripts/diagnose.sh
```

The default global companion is `~/Library/Application Support/PCB-Project-Template`
on macOS, or `$XDG_DATA_HOME/PCB-Project-Template` on Linux. Override with
`KICAD_KIT_HOME`. It contains the optional venv, project registry, manually
installed plugin checkouts and template environment snippet. This is separate
from KiCad's own versioned user plugin directory. No venv, app, plugin checkout,
PCM state, Git internals or generated manufacturing data is copied into projects.

`requirements.txt` remains a valid comments-only pip file. Optional IPC packages
are declared in `tools/requirements-ipc.txt`; the installer uses the tested transitive resolution in `tools/requirements-ipc-lock.txt` (macOS arm64 / Python 3.13.5). Other platforms may need a separately reviewed resolution. Install neither `pcbnew` nor a second
wxPython into the kit environment: legacy action plugins use KiCad's runtime.
