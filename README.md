<div align="center">

<h1>⚡ PCB Project Template</h1>

<p><strong>Ein klarer Start für dein nächstes Board.</strong></p>
<p>KiCad · Hardware · Firmware · Dokumentation · Fertigung</p>

<p>
  <a href="https://www.kicad.org/"><img src="https://img.shields.io/badge/KiCad-10.0.7-314CB0?style=for-the-badge" alt="KiCad 10.0.7"></a>
  <a href="requirements.txt"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python ab 3.10"></a>
  <a href="docs/INSTALLATION.md"><img src="https://img.shields.io/badge/Setup-macOS-222222?style=for-the-badge&amp;logo=apple&amp;logoColor=white" alt="Setup für macOS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2E8B57?style=for-the-badge" alt="MIT-Lizenz"></a>
</p>

<p>
  <a href="#installation"><strong>Loslegen</strong></a>
  &nbsp; · &nbsp;
  <a href="#drei-vorlagen">Vorlagen</a>
  &nbsp; · &nbsp;
  <a href="#dokumentation">Dokumentation</a>
  &nbsp; · &nbsp;
  <a href="#tests">Tests</a>
</p>

</div>

---

## Aus meiner PCB-Praxis entstanden

Ich habe dieses Template auf Basis meiner bisherigen Erfahrungen im PCB-Design
und der Arbeit an eigenen Hardwareprojekten erstellt. Dabei wollte ich die
wiederkehrenden Aufgaben rund um ein Board an einem Ort zusammenbringen:
eine verständliche Projektstruktur, nachvollziehbare Bauteilquellen,
Hardware-/Firmware-Schnittstellen, Dokumentation und reproduzierbare Prüfungen.

Mein Ziel ist, bei einem neuen Projekt direkt mit der Entwicklung beginnen zu
können, statt jedes Mal die Ablage und die grundlegenden Werkzeuge neu
aufzusetzen. Dieses Repository hält dafür meinen bisherigen Arbeitsstand fest
und lässt sich mit den Erfahrungen aus weiteren Projekten weiterentwickeln.

Wenn du vor ähnlichen Aufgaben stehst, kannst du das Template als Ausgangspunkt
verwenden und an deinen eigenen Entwicklungsablauf anpassen.

| 🧩 Strukturiert starten | 🔎 Nachvollziehbar prüfen | 📦 Geordnet weitergeben |
| :---: | :---: | :---: |
| Hardware, Firmware und Unterlagen haben feste Ablageorte. | ERC/DRC und Exporte erhalten Protokolle und Dateihashes. | Eigenständige Boardprojekte mit dokumentiertem Entwicklungsstand. |

---

---

## Was das Template bereitstellt

| Nutzen im Alltag | Umsetzung |
| --- | --- |
| Ein neues Board in Sekunden anlegen | Drei Vorlagen (Generic PCB, STM32 Embedded, Arduino Shield) erzeugen eigenständige Projekte – per Doppelklick auf `project-manager.command`, per `scripts/kit create` oder in KiCad über **File > New Project from Template**. Vorhandene Ordner werden nie überschrieben. |
| Dieselben Prüfungen bei jeder Revision | `scripts/kit verify` führt ERC, DRC mit Schaltplan-Abgleich sowie Prüfungen auf Bibliotheksreferenzen, Footprints, Bauteil-Metadaten, 3D-Modelle und BOM aus. Jede Prüfung ist pro Projekt als *required*, *advisory* oder *disabled* konfigurierbar. |
| Fertigungsdaten mit bekanntem Stand | `scripts/kit export` erzeugt Gerber, Bohrdaten, BOM, Bestückungsdaten, Bestückungszeichnungen, STEP, Schaltplan-PDF, Netzliste und Interactive HTML BOM – mit Manifest, SHA-256-Werten und Reproduzierbarkeitsvergleich. |
| Entwurf und Freigabe klar trennen | Exporte sind standardmäßig `DRAFT` / `NO-GO`. Eine `GO`-Ausgabe verlangt `--authorize`, eine signierte Freigabedatei zur exakten Revision und zum Commit, einen sauberen Git-Stand und bestandene Prüfungen. |
| Plugins und Umgebung im Blick | Der Installer prüft KiCad 10.0.7, richtet `.venv` ein, installiert die Vorlagen, ruft InteractiveHtmlBom, Freerouting und KiKit tatsächlich auf und diagnostiziert die KiCad-IPC-Schnittstelle. |
| Thermische Abschätzung | `scripts/kit thermal analyze` berechnet aus dem echten Layout und deinen Verlustleistungen ein stationäres Temperaturfeld (Heatmaps oben/unten, Hotspots, Bauteiltemperaturen, HTML-Bericht) und vergleicht Läufe vor/nach Layoutänderungen. Ergebnisse sind **Schätzungen** und ersetzen keine Messung. |
| Hardware und Firmware gemeinsam | Die MCU-Vorlagen trennen plattformunabhängige Anwendung (`firmware/app`), BSP-Schnittstelle und Ziel-BSP; Host-Unit-Tests laufen mit CMake, Arduino baut mit PlatformIO. |

Du bekommst einen **Designstart, keine fertige Schaltung**. Eine leere Platine
scheitert erwartungsgemäß am DRC, solange die Kontur fehlt. Bestandene
ERC/DRC-Prüfungen sind Werkzeugergebnisse – sie ersetzen keine elektrische,
thermische oder mechanische Validierung und keinen Prototypentest.

## Installation

Voraussetzungen: macOS, KiCad **10.0.7** unter `/Applications/KiCad/`,
Python ≥ 3.10, Git. Beim ersten Lauf wird Internet für `pip` benötigt.

```sh
./install_template.command      # oder Doppelklick im Finder
```

Der Installer ist idempotent: Ein zweiter Lauf meldet `UNCHANGED` und ändert
nichts. Fremde Ordner im KiCad-Template-Verzeichnis bleiben unberührt, KiCad-
Einstellungen werden nicht verändert. Details: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Schnellstart

```sh
./project-manager.command                          # interaktives Menü

# oder nicht-interaktiv (reproduzierbar, mit --json für Automatisierung)
scripts/kit create --template stm32-embedded --profile 4-layer --name "Mein Board" --dest "$HOME/Projects/Mein Board"
scripts/kit open    "$HOME/Projects/Mein Board"            # KiCad (oder --vscode)
scripts/kit verify  "$HOME/Projects/Mein Board"            # Qualitätsprüfungen
scripts/kit export  "$HOME/Projects/Mein Board" --revision A1
scripts/kit releases "$HOME/Projects/Mein Board"           # CURRENT oder STALE?
scripts/kit firmware "$HOME/Projects/Mein Board" --target host
scripts/kit doctor                                          # Umgebung prüfen
```

`--git` beim Anlegen führt nur `git init` aus; das Template erstellt niemals
Commits und pusht nichts. `--profile` wählt ein **Beispiel**-Profil
(`2-layer` Standard, `4-layer`) mit Lagenaufbau, Mindestregeln und Netzklassen –
`scripts/kit templates profiles` zeigt die Werte. Sie sind mit dem Fertiger
abzustimmen, nicht universell richtig.

## Der erste Entwurf – Schritt für Schritt

1. **Installieren:** `./install_template.command` (einmalig; erneut ausführen nach Updates).
2. **Projekt anlegen:** `./project-manager.command` → *Create project* → Vorlage →
   Board-Profil (`2-layer` oder `4-layer`) → Name → Ordner. In KiCad über
   *File > New Project from Template* entsteht immer das `2-layer`-Profil;
   für vier Lagen den Projektmanager oder `scripts/kit create --profile 4-layer` nutzen.
3. **In KiCad öffnen:** `scripts/kit open "<Projekt>"` (öffnet bei laufendem KiCad
   im vorhandenen Fenster – vorher eigene Arbeit speichern).
4. **Schaltplan:** Bauteile platzieren, `Footprint`, `Datasheet`, `Manufacturer`,
   `MPN` eintragen (siehe `docs/engineering/`), annotieren, ERC im Editor.
5. **Board:** *Tools > Update PCB from Schematic* (F8), Kontur auf `Edge.Cuts`
   zeichnen, in *Board Setup* Lagenaufbau und Regeln mit dem Fertiger abgleichen,
   platzieren, routen, Zonen füllen, speichern.
6. **Prüfen:** `scripts/kit verify "<Projekt>"`. Ein neues, leeres Board meldet
   `invalid_outline`, bis Schritt 5 eine Kontur hat – das ist erwartet.
7. **Fertigungsdaten:** `scripts/kit export "<Projekt>" --revision A1`, dann
   `scripts/kit releases "<Projekt>"` (muss `CURRENT` zeigen).
8. **Freigabe:** Review, signierte Freigabedatei, `--approval … --authorize`
   (siehe `docs/MANUFACTURING.md`).

Projekte bei geöffnetem Editor nicht automatisiert prüfen: KiCads Lock-Dateien
führen dann bewusst zum Abbruch (Exit 14).

## Drei Vorlagen

| Vorlage | Inhalt |
| --- | --- |
| `generic-pcb` | Leerer, von KiCad 10.0.7 erzeugter Schaltplan und PCB – unabhängig von einem Mikrocontroller. |
| `stm32-embedded` | Leeres Board plus CMake-Presets, plattformunabhängiges Anwendungsmodul mit Host-Tests und Anbindung an ein STM32CubeMX-Projekt. MCU und Pinbelegung werden nicht vorgegeben. |
| `arduino-shield` | Basierend auf KiCads offizieller Vorlage *Arduino Uno Shield* (Kontur, Steckverbinder, Bohrungen; © Caleb Reister, Jonathan Iapicco), plus PlatformIO-Firmware. |

Jedes Projekt erhält `hardware/`, `firmware/`, `components/`, `manufacturing/`,
`docs/` (inklusive `docs/engineering/` mit den Entwurfsrichtlinien) und `qa/`. Werkzeuge, Plugins und virtuelle Umgebungen werden nicht in
Projekte kopiert. Aufbau: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Dokumentation

| Thema | Dokument |
| --- | --- |
| **Entwurfsrichtlinien** (Bauteilauswahl, Datenblatt-Checkliste, Schaltplan, Platzierung, Routing, Fertigung, Lessons Learned) | [docs/engineering/README.md](docs/engineering/README.md) |
| Architektur und Modulgrenzen | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Installation | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| Repository- und Projektaufbau | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| Bibliotheken und Portabilität | [docs/LIBRARY_MANAGEMENT.md](docs/LIBRARY_MANAGEMENT.md) |
| KiCad-Versionspolitik | [docs/KICAD_COMPATIBILITY.md](docs/KICAD_COMPATIBILITY.md) |
| Referenzprojekte | [qa/fixtures/README.md](qa/fixtures/README.md) |
| Plugins (IBOM, Freerouting, KiKit, KiBuzzard, Board2Pdf, KiBot, optionale) | [docs/PLUGIN_MANAGEMENT.md](docs/PLUGIN_MANAGEMENT.md) |
| KiCad-IPC-API | [docs/KICAD_IPC.md](docs/KICAD_IPC.md) |
| Alle Befehle und Exit-Codes | [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) |
| Fertigung und Freigabe | [docs/MANUFACTURING.md](docs/MANUFACTURING.md) |
| Thermische Analyse | [docs/THERMAL_ANALYSIS.md](docs/THERMAL_ANALYSIS.md) |
| Prüfungen und Testsuite | [docs/VERIFICATION.md](docs/VERIFICATION.md) |
| Fehlersuche | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Erkenntnisse | [docs/LESSONS_LEARNED.md](docs/LESSONS_LEARNED.md) |
| Umsetzungsstand und Abnahme | [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md), [docs/ACCEPTANCE_REPORT.md](docs/ACCEPTANCE_REPORT.md) |
| Regeln für Code-Agenten | [AGENTS.md](AGENTS.md) |

## Tests

```sh
python3 test_template.py          # komplette Suite, inkl. echter KiCad-Tests
KICAD_NATIVE_TESTS=0 python3 test_template.py   # ohne KiCad-Integration
```

Die nativen Tests nutzen `qa/fixtures/divider`, ein ausschließlich aus KiCads
offiziellen Bibliotheken erzeugtes Werkzeug-Fixture (keine geprüfte Schaltung).
Sie führen echtes ERC/DRC, alle Exporte, Reproduzierbarkeitsvergleiche und
Plugin-Aufrufe aus. Tests schreiben nie in echte Benutzereinstellungen.
