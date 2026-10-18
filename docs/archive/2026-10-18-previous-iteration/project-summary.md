# Projektstand und Zusammenfassung

Stand: 18. Oktober 2026. Diese Übersicht beschreibt den aktuellen Arbeitsstand.
`baseline-inventory.json` dokumentiert dagegen den ursprünglichen Zustand;
`implementation-report.md` ist der historische Bericht der ersten Erweiterung.

## Was entstanden ist

Aus dem ursprünglichen KiCad-Starter ist ein wiederverwendbares Template mit
Engineering-Unterlagen und ausführbaren Werkzeugen geworden. Die bestehende
Aufteilung wurde beibehalten: native Projektdateien im Stamm eines erzeugten
Boardprojekts, ergänzende Inhalte unter hardware, firmware, components, docs,
qa und manufacturing. Shell-Einstiegspunkte liegen unter scripts, gemeinsame
Python-Implementierungen unter tools.

- Native Template-Installation über `install_template.command`, einschließlich
  Wiederholungsprüfung und Schutz vorhandener Benutzerdateien.
- Interaktive oder parametrierte Projekterstellung mit echten KiCad-generierten
  Leerdateien, optionalem Git-Start und globalem Projektregister.
- Versionsprüfung für KiCad 10.0.7, ERC, DRC und Schaltplan-/PCB-Abgleich mit
  eigenen Prüflaufordnern, Befehlsprotokollen und Quell-Dateihashes.
- BOM-, Gerber-, Bohrdaten-, Positions- und STEP-Exporte mit Revision und Manifest.
  Entwürfe bleiben NO-GO; GO erfordert zusätzliche Nachweise und erfolgreiche
  Prüfungen. Menschliche Unterschriften oder Messwerte werden nicht authentifiziert.
- Globale Plugin-Verwaltung für InteractiveHtmlBom und FreeRouting, einschließlich
  Diagnose vorhandener PCM-Pakete und konservativer manueller Installation.
- Projektbezogene Bibliotheksregistrierung mit `${KIPRJMOD}`-Pfaden.
- Optionale Build-Adapter für tatsächliche STM32/CMake- und Arduino-Projekte.
- IPC-Diagnose über einen echten Ping und Versionsabfragen, ohne Designmutation.

## Installierte Umgebung auf diesem Mac

Die dauerhafte venv liegt außerhalb des Templates:

```text
~/Library/Application Support/PCB-Project-Template/venv
```

Sie enthält `kicad-python==0.8.0` und die festgelegten Abhängigkeiten aus
`tools/requirements-ipc-lock.txt`. Die Grundwerkzeuge benötigen nur die
Python-Standardbibliothek. KiCad und seine Legacy-Plugin-Laufzeit sind getrennt.
Die externe venv wird nicht in erzeugte Boardprojekte kopiert.

Bei der aktuellen Diagnose wurde KiCad 10.0.7 gefunden. Die PCM-Konfiguration
meldet InteractiveHtmlBom 2.12.0 und FreeRouting 2.4.1; beide Payload-Verzeichnisse
sind vorhanden. Das bestätigt Installation und Metadaten, keinen erfolgreichen
Plugin-Lauf. Der Live-IPC-Verbindungsversuch meldet weiterhin UNAVAILABLE mit
Connection refused. Die frühere Konfigurationsprüfung ergab `enable_server: false`.
Zum Testen API aktivieren, eine Platine im PCB Editor öffnen und den Diagnosebefehl
aus `docs/ipc.md` mit der venv ausführen.

## Bereinigung

- Die nützlichen Inhalte von `README Kopie.md` wurden nach ausdrücklicher
  Freigabe in die Haupt-README übernommen; die Kopie wurde entfernt.
- Doppelte deutsch/englische README-Abschnitte wurden zusammengeführt. Die README
  erklärt Nutzen, Grenzen, Einstieg und verweist für Details auf Fachdateien.
- Rechnerbezogene Statusmeldungen stehen in dieser Übersicht und in generierten
  Diagnoseberichten, nicht als Voraussetzung in der wiederverwendbaren Anleitung.
- `requirements.txt` bleibt pip-kompatibel und kommentarbasiert; widersprüchliche
  Angaben zu benötigtem Python wurden entfernt. Optionale IPC-Abhängigkeiten
  stehen weiterhin getrennt in ihren vorhandenen Requirements-Dateien.
- Unbenutzte Python-Imports und Variablen wurden entfernt; dynamische JSON-/Path-
  Imports durch normale Imports ersetzt. Öffentliche Einstiegspunkte blieben erhalten.
- Die PCM-Diagnose verwendet jetzt die native Konfigurationsdatenbank statt
  vorrangig einer veralteten Datei im Plugin-Datenverzeichnis. Zwei Regressionstests
  prüfen die Priorität und den Rückfall auf den bisherigen Pfad.
- Die bereits im Arbeitsbereich ergänzte Copyright-Namensangabe in `LICENSE`
  wurde unverändert erhalten. Der historische Inventarhash bleibt erhalten;
  der Regressionstest akzeptiert gezielt den aktuellen Dateihash.
- Historische Inventare und Prüfnachweise bleiben erhalten. Kein Commit, Push,
  App-Upgrade, Plugin-Update oder Eingriff in offene KiCad-Designs wurde ausgeführt.

## Grenzen und nächste fachliche Arbeit

Das Template ist ein leerer Projektstart. Es enthält weder eine entwickelte
Schaltung noch eine validierte MCU-Firmware. Ein neues leeres Board scheitert
korrekt am DRC, solange die Kontur fehlt. Reale Bauteile, Regeln, Pinmaps,
Anforderungen, Toolchains und Nachweise müssen projektbezogen bearbeitet werden.

Offen sind ein erfolgreicher Live-IPC-Verbindungstest, echte Plugin-Läufe,
zielbezogene Firmware-Builds sowie elektrische, mechanische und thermische
Validierung eines tatsächlichen Boards. Native Testexporte einer rechteckigen
mechanischen Testplatine sind keine Fertigungsfreigabe.

## Prüfung dieses Arbeitsstands

Die fünf ursprünglichen Strukturtests und alle 24 Regressions-/Integrationstests
bestanden nach der Bereinigung (29 Tests insgesamt, native Tests aktiviert).
Dabei wurden echte ERC-/DRC-Ergebnisse, der erwartete Fehler am leeren Board,
der erfolgreiche Kontur-Test und alle Exportarten geprüft. Zusätzlich waren
`pip check`, lokale Dokumentationslinks und `git diff --check` erfolgreich.
Der direkte Start von `qa/tests/test_tools.py` führt nun ebenfalls alle dort
definierten Testklassen aus, nicht nur die erste.

Die aktuellen Ausführungsprotokolle liegen unter `qa/generated/cleanup-*.log`
und die Diagnose unter `qa/generated/cleanup-diagnostics.json`. Sie werden nicht
in Quellarchive übernommen. Die Quelltests und die unabhängigen nativen Tests
lassen sich wie in der README erneut ausführen. Ältere ZIP-Dateien bleiben
Momentaufnahmen des damaligen Stands; neue Archive entstehen über `scripts/package.sh`.
