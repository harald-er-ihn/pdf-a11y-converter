# 🛠️ PDF A11y Converter

[![Pylint Score](https://img.shields.io/badge/pylint-10.00%2F10.00-brightgreen)](https://pylint.pycqa.org/)
[![PDF/UA-1](https://img.shields.io/badge/compliance-PDF%2FUA--1-blue)](https://pdfa.org/)
[![Architecture](https://img.shields.io/badge/architecture-Clean%20Architecture-orange)](#)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**Eine autarke, KI-gestützte Enterprise-Lösung zur PDF/UA-1 Rekonstruktion.**  
*Strikte Clean Architecture. Absolute Datenhoheit. Integrierte Endabnahme.*

---

## 📥 Download (Standalone Versionen)

Für Windows und macOS stellen wir komplett vorkompilierte, 100% offline-fähige Pakete zur Verfügung. 
Da die integrierten KI-Modelle (PyTorch, YOLO, NLLB, etc.) für den lokalen Betrieb sehr groß sind, hosten wir die Pakete (ca. 1,0 GB) auf einem dedizierten High-Speed Cloud-Speicher der TU Dortmund.

> 🔒 **Download-Passwort:** Aus Sicherheitsgründen erfordert der Universitäts-Server ein Passwort für den Download. Bitte nutze: **yBmqxDneq2**

### 🪟 Windows 11
- [⬇️ Download PDF-A11y-Converter (Windows) .zip](https://tu-dortmund.sciebo.de/s/ijbi8cCZgHazMtr)
- **SHA256:** `7a15f547b61f46cf8646540aa3e208e32c914b953f81cdd248cc642134c85905`

### 🍎 macOS (Apple Silicon & Intel)
- [⬇️ Download PDF-A11y-Converter (macOS) .zip](https://tu-dortmund.sciebo.de/s/GqCmHs7PK9pwKFr)
- **SHA256:** `b071f98561597bdd90348a9c44774f717b7a01329f0428cab7e2b2d80bea0b4d`

<details>
<summary><b>🍏 Besonderer Hinweis für macOS-Nutzer (Apple Gatekeeper)</b></summary>

Da dieses Tool ein echtes, lokales Open-Source-Projekt ist, verzichten wir auf kostenpflichtige Apple-Entwicklerzertifikate. 
MacOS markiert heruntergeladene Programme aus dem Internet standardmäßig mit einem Quarantäne-Flag. 
Beim ersten Start erscheint daher möglicherweise die Meldung:
*"Kann nicht geöffnet werden, da der Entwickler nicht verifiziert werden kann."*

**Lösung:**
1. Mache einen **Rechtsklick** auf die App `PDF-A11y-GUI`.
2. Klicke im Kontextmenü auf **"Öffnen"**.
3. Bestätige den folgenden Sicherheitsdialog mit **"Trotzdem öffnen"**.
</details>

---

## 🎯 Die Vision: Das "Semantic Overlay" Prinzip

Die nachträgliche Barrierefrei-Machung von PDFs scheitert meist an einem massiven Dilemma: 
Baut man das PDF neu auf, zerstört man das exakte visuelle Layout. Nutzt man Cloud-Tools, verliert man die Datenhoheit.

Der **PDF A11y Converter** löst dieses Problem durch das **Semantic Overlay Pattern**:
1. **100% Visual Fidelity:** Das optische Erscheinungsbild des Original-PDFs bleibt auf den Pixel genau erhalten.
2. **Semantische Tiefe:** Das Tool generiert einen komplett unsichtbaren, perfekten PDF/UA-1 Strukturbaum und stempelt das visuelle Original als für Screenreader unsichtbares Grafikelement (`/Artifact`) in den Hintergrund.

## 🧠 Architektur: Clean Architecture & Plugin Discovery

Das System ist nach modernsten Software-Engineering-Standards in strikt getrennte Schichten (Application, Infrastructure, Plugins) unterteilt. 
Jeder Spezialist läuft in einem isolierten `venv`. Die Engine scannt verfügbare KI-Modelle dynamisch via `manifest.json`, validiert die Daten via *Pydantic* 
und bindet die Worker zur Laufzeit als **Plugins** in die hochgradig parallelisierte Sensor-Fusion ein.

![Architektur des PDF A11y Converters](static/img/architecture_graph.svg)

## ✨ Enterprise Kern-Features

- **100% Native & Offline:** Keine Server, kein Docker, keine Cloud. Das gesamte Tool läuft nativ in Python auf dem lokalen System. 
Alle KI-Frameworks werden durch harte Environment-Blocker an der Telemetrie gehindert (DSGVO & BSI konform).
- **Multi-Core Parallelisierung:** Die KI-Worker laufen nicht nacheinander, sondern werden asynchron und parallel über alle verfügbaren CPU-Kerne verteilt.
- **Graceful Degradation & Error Contracts:** Stürzt eine KI ab (z.B. GPU Out-of-Memory), fängt das System den Fehler via JSON-Contract ab. Die Konvertierung läuft mit Fallback-Werten stabil weiter.
- **Maschinenlesbarer Audit-Trail:** Für jedes PDF wird eine `audit.json` generiert, die Laufzeiten, GPU-Status und alle KI-Entscheidungen revisionssicher protokolliert.
- **Integrierte Endabnahme:** Jedes Dokument wird lokal durch den offiziellen **veraPDF** Validator maschinell geprüft.

## 🛠️ Die KI-Experten (Worker-Pool)

- **Layout & Struktur:** `docling` (IBM) und `marker-pdf`
- **Tabellen-Präzision:** `pdfplumber`
- **Wissenschaftliche Formeln:** `nougat-ocr` (Meta)
- **Lokale Fußnoten-Heuristik:** `PyMuPDF`
- **Bild-Beschreibungen:** `BLIP` (Salesforce)
- **Formulare & Vektoren:** `pikepdf`
- **Handschriften & Signaturen:** `YOLOv8s` (Lokales Offline-Modell)
- **i18n Übersetzung:** `NLLB-200` (Meta) 

## 🚀 Installation & Nutzung (für Entwickler)

*Voraussetzung: Python 3.12+, Linux/macOS/Windows.*

```bash
# 1. Repository klonen
git clone https://github.com/harald-er-ihn/pdf-a11y-converter.git
cd pdf-a11y-converter

# 2. Main-Environment einrichten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# 3. Experten-Worker initialisieren (Baut die isolierten Venvs)
./tools/rebuild_worker_venvs.sh

# 4. CLI nutzen
python cli.py eingabe.pdf -o ausgabe_pdfua.pdf -v
```

## 👥 Zielgruppe

Dieses Tool richtet sich an:
- **Accessibility Engineers**, die eine skalierbare, datenschutzkonforme Pipeline benötigen.
- **Behörden & Universitäten**, die das Barrierefreiheitsstärkungsgesetz (BFSG) lokal umsetzen müssen.
- **Software-Architekten**, die Best-Practices im Umgang mit isolierten KI-Workern und Sensor-Fusion suchen.


## ☕ Support & Spenden
Dieses Projekt ist zu 100% Open-Source. Es gibt keine Paywalls und keinen versteckten Cloud-Zwang.

Wenn dir dieses Tool die Arbeit erleichtert hat oder du die Weiterentwicklung unterstützen möchtest, freue ich mich über einen Kaffee:
![alt text](https://img.shields.io/badge/Donate-PayPal-blue.svg?logo=paypal&style=for-the-badge)

© 2026 Dr. Harald Hutter

