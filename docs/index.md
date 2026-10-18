# ⚡ PCB Project Template – Dokumentation

<div class="kit-hero">
  <p><strong>Ein klarer, reproduzierbarer Start für professionelle Hardware- und Firmware-Entwicklung mit KiCad 10.0.7 auf macOS.</strong></p>
  <p>Verlässliche Projektstruktur, automatisierte Verification Gates (ERC/DRC mit Schaltplan-Parität), autorisierte Fertigungsfreigaben mit SHA-256-Manifesten und Steuerung via CLI (<code>scripts/kit</code>) sowie moderner Desktop-Manager GUI.</p>
</div>

## Willkommen

Das **PCB-Project-Template** ist eine erprobte Entwicklungsvorlage für macOS, die wiederkehrende Aufgaben rund um ein Board an einem Ort zusammenführt:

- **Verlässliche Projektstruktur:** Klare Ablage für Schaltplan, Board, Firmware (HAL/BSP getrennt von Anwendungslogik), Bibliotheken und Fertigungsunterlagen.
- **Reproduzierbare Prüfungen:** Automatisierte Verification Gates (ERC, DRC mit Schaltplan-Parität, Footprint-Validierung, 3D-Modelle, Bauteil-Metadaten).
- **Geordnete Fertigung:** Gezielte Trennung zwischen vorläufigen Entwürfen (<code>DRAFT</code> / <code>NO-GO</code>) und geprüften, autorisierten Freigaben (<code>GO</code>) mit lückenlosen Manifesten und SHA-256-Prüfsummen.
- **Bedienung nach Wahl:** Volle Funktionalität über die Befehlszeile (<code>scripts/kit</code>), interaktive Skripte sowie einen modernen Desktop-Manager (<code>scripts/kit gui</code>).

---

## Dokumentationsübersicht

<div class="kit-cards-grid">
  <a class="kit-card" href="ARCHITECTURE.md">
    <h3>📐 Architektur & Grundlagen</h3>
    <p>Grundsätze, Tool-Paketierung, Invarianten und Verzeichnisstrukturen des Projekts.</p>
    <div class="kit-card-footer">Dokumentation öffnen →</div>
  </a>
  <a class="kit-card" href="INSTALLATION.md">
    <h3>🛠️ Installation & Bedienung</h3>
    <p>Setup für macOS, CLI-Referenz (<code>scripts/kit</code>), Desktop-GUI und PCM-Plugins.</p>
    <div class="kit-card-footer">Dokumentation öffnen →</div>
  </a>
  <a class="kit-card" href="VERIFICATION.md">
    <h3>🛡️ Qualität & Fertigung</h3>
    <p>Automatisierte Verification Gates (ERC/DRC), Gerber-Exporte und Freigabeprozesse.</p>
    <div class="kit-card-footer">Dokumentation öffnen →</div>
  </a>
  <a class="kit-card" href="IMPLEMENTATION_STATUS.md">
    <h3>📋 Status & Berichte</h3>
    <p>Implementierungsstand aller Module, Abnahmetests und gesammelte Erfahrungen.</p>
    <div class="kit-card-footer">Dokumentation öffnen →</div>
  </a>
</div>

### 📐 Architektur & Grundlagen
- [**Architektur (ARCHITECTURE.md)**](ARCHITECTURE.md) – Grundsätze, Tool-Paketierung, Invarianten und Designentscheidungen.
- [**Projektstruktur (PROJECT_STRUCTURE.md)**](PROJECT_STRUCTURE.md) – Verzeichnisaufbau, Ablageorte für Hardware, Firmware, Komponenten und Doku.
- [**KiCad 10 Kompatibilität (KICAD_COMPATIBILITY.md)**](KICAD_COMPATIBILITY.md) – Spezifische Anforderungen für KiCad 10.0.7.

### 🛠️ Installation & Bedienung
- [**Installation & Setup (INSTALLATION.md)**](INSTALLATION.md) – Schritt-für-Schritt-Anleitung für macOS, Python-Venv und Toolchains.
- [**CLI-Referenz (CLI_REFERENCE.md)**](CLI_REFERENCE.md) – Alle Befehle (`create`, `verify`, `export`, `doctor`, `gui` u. a.) im Detail.
- [**GUI-Abnahmetest (GUI_ACCEPTANCE.md)**](GUI_ACCEPTANCE.md) – Anleitung und Checkliste für die Desktop-Anwendung.
- [**Bibliotheksverwaltung (LIBRARY_MANAGEMENT.md)**](LIBRARY_MANAGEMENT.md) – Portabilität über `${KIPRJMOD}`, lokale Symbole und Footprints.
- [**Plugin-Verwaltung (PLUGIN_MANAGEMENT.md)**](PLUGIN_MANAGEMENT.md) – KiCad PCM-Erweiterungen (InteractiveHtmlBom, Freerouting, KiKit).
- [**KiCad API & IPC (KICAD_IPC.md)**](KICAD_IPC.md) – Live-Schnittstellen und Fallback-Verhalten.

### 🛡️ Qualität & Fertigung
- [**Verifikation & Quality Gates (VERIFICATION.md)**](VERIFICATION.md) – ERC, DRC, Netzlisten-Parität und Release-Kriterien.
- [**Fertigung & Releases (MANUFACTURING.md)**](MANUFACTURING.md) – Gerber, Bohrdaten, BOM, Bestückungskoordinaten und DRAFT/GO-Freigabeprozess.
- [**Thermische Analyse (THERMAL_ANALYSIS.md)**](THERMAL_ANALYSIS.md) – Finite-Differenzen-Schätzung für Verlustleistungen.
- [**Fehlerbehebung (TROUBLESHOOTING.md)**](TROUBLESHOOTING.md) – Lösungen für häufige Fehler und Warnungen.

### 📋 Status & Berichte
- [**Implementierungsstatus (IMPLEMENTATION_STATUS.md)**](IMPLEMENTATION_STATUS.md) – Aktueller technischer Stand aller Komponenten.
- [**Abnahmebericht (ACCEPTANCE_REPORT.md)**](ACCEPTANCE_REPORT.md) – Detaillierte Testergebnisse und Validierungsprotokolle.
- [**Lessons Learned (LESSONS_LEARNED.md)**](LESSONS_LEARNED.md) – Erfahrungen aus der PCB-Praxis und Template-Entwicklung.

---

## Die drei Board-Vorlagen

| Vorlage | Profil | Typischer Einsatzzweck |
| :--- | :--- | :--- |
| **`generic-pcb`** | 2 Lagen, 1.6 mm FR-4 | Mikrocontroller-unabhängiges Universalboard mit vollständiger Ordnerstruktur. |
| **`stm32-embedded`** | 4 Lagen, Standard-Stackup | Embedded-Systeme mit STM32; getrennte HAL/BSP-Firmware-Ordnerstruktur. |
| **`arduino-shield`** | 2 Lagen (KiCad-Katalog) | Standardisiertes Shield mit Uno-kompatiblen Steckverbindern. |

---

## Schnelleinstieg

```bash
# 1. Repository klonen
git clone https://github.com/CagriCatik/PCB-Project-Template.git
cd PCB-Project-Template

# 2. Python-Umgebung einrichten
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-gui.txt

# 3. Umgebung prüfen
scripts/kit doctor

# 4. GUI oder CLI starten
scripts/kit gui
# oder per CLI:
scripts/kit templates
```
