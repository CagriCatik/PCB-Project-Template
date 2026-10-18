# Global plugin management

`tools/plugins.py` centralizes the selected catalog, diagnostics, legacy Git
installation and checksum-verified archive installation. Nothing installs at
module import time. Plugins are never vendored into generated board projects.

The catalog is `tools/plugins.json`. It includes **InteractiveHtmlBom** for
assembly inspection and **FreeRouting** for optional autorouting. The catalog
records plugin identities; installed PCM state remains owned by KiCad.

```sh
./scripts/install-plugins.sh --diagnose
./scripts/install-plugins.sh  # InteractiveHtmlBom v2.12.0; existing --dest/--source options retained
```

The default plugin directory on macOS is
`~/Documents/KiCad/10.0/scripting/plugins`. `KICAD_DOCUMENTS_HOME` changes the
versioned user data root; pass `--dest` for another scripting directory or
`--user-root` for diagnostics/archive installation. Confirm actual search paths
in the PCB scripting console with
`import pcbnew; print(pcbnew.PLUGIN_DIRECTORIES_SEARCH)`.

InteractiveHtmlBom's [upstream installation instructions](https://github.com/openscopeproject/InteractiveHtmlBom/wiki/Installation)
allow a checkout linked into the scripting path. This installer checks the
repository origin, pinned tag, clean checkout and existing link before reuse.
It does not silently update or replace anything. The [2.12.0 release](https://github.com/openscopeproject/InteractiveHtmlBom/releases/tag/v2.12.0)
includes KiCad 10 support. Restart PCB Editor to discover newly installed plugins.

For FreeRouting, use Tools > Plugin and Content Manager and choose the official
Freerouting integration. Java requirements depend on the packaged router version;
consult the [upstream integration](https://github.com/freerouting/freerouting/tree/master/integrations/KiCad).
Diagnostics reports actual `java -version` output, not an assumed Java minimum.
An existing directory alone does not prove the package loads or supports your
board. Automatic routing is never invoked by this kit.

For reproducible offline installation of a reviewed legacy action-plugin PCM ZIP:

```sh
./scripts/install-plugins.sh --plugin freerouting --archive /path/to/package.zip --sha256 PUBLISHED_SHA256
```

The same archive interface supports `--plugin interactivehtmlbom`. It checks the
hash, package identity, declared KiCad compatibility, safe archive paths, payload
limits and Python entry point. It installs a **manual** scripting plugin plus an
install marker; it does not claim PCM ownership or edit `installed_packages.json`.
Packages requiring extra runtime/library payloads or IPC plugin registration are
refused and should use PCM. Metadata compatibility is a declaration, not a tested
runtime guarantee. Retain the exact ZIP and digest for reproducibility.

If a PCM package already exists, scripts report PCM_MANAGED and leave updates and
removal to PCM. A missing PCM version in diagnostics means no matching database
entry; it is not filled with an invented version. Avoid duplicate installations.
To remove a manual installation, remove only its named symlink/payload; keep the
checkout if needed. The installer provides no blanket deletion command.

PCM diagnostics reads `installed_packages.json` from KiCad's versioned configuration
directory (on macOS `~/Library/Preferences/kicad/10.0`), independently of the user
plugin payload directory. `KICAD_CONFIG_HOME` selects another configuration base.
The older `3rdparty/installed_packages.json` location is used only as fallback.
The diagnostic JSON names the actual `package_database` used.
