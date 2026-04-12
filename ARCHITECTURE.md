# 🏛️ System Architecture: PDF A11y Converter

Dieses Dokument beschreibt die architektonischen Designentscheidungen, Patterns und Datenflüsse des PDF A11y Converters. 

Das System wurde nach den Prinzipien der **Clean Architecture** (Ports & Adapters) entwickelt. Das oberste Paradigma bei der Entwicklung war: **Qualität, Isolation, Auditierbarkeit und Stabilität vor Komplexität.**

## 1. Clean Architecture & Plugin Discovery

Um Dependency-Hell und Monolithen-Verfall zu verhindern, ist die Architektur in strikte Schichten unterteilt:
- **Application Layer (`src/application/`)**: Enthält ausschließlich die Geschäftslogik (den `SemanticOrchestrator`). Sie weiß *was* zu tun ist, aber nicht *wie* es technisch umgesetzt wird.
- **Infrastructure Layer (`src/infrastructure/`)**: Implementiert die technischen Details (WeasyPrint, veraPDF, Dateisystem-Zugriffe, PyMuPDF-Adapter).
- **Plugin Layer (`src/plugins/`)**: Verwaltet die isolierten KI-Experten.

**Dynamisches Worker-Discovery:**
Die Engine kennt die KI-Worker nicht mehr hardcodiert. Stattdessen scannt ein `PluginManager` beim Start das Verzeichnis `workers/`. Jeder Worker besitzt eine `manifest.json` (Contract), die seine Fähigkeiten, seine Ausführungsphase (`map` oder `reduce`) und sein striktes Laufzeit-Timeout definiert. Neue KI-Modelle können somit als Drop-In Plugins hinzugefügt werden.

## 2. Das "Semantic Overlay" Pattern (Generator)

Die klassische Erstellung von barrierefreien PDFs basiert auf HTML-to-PDF-Engines, die den Text neu setzen (Reflow). Das zerstört jedoch oft das originäre Corporate Design. Dieses Projekt geht einen völlig anderen Weg:

1. Die Worker extrahieren millimetergenaue Koordinaten (Bounding Boxes) aller Elemente aus dem Original-PDF.
2. Der Generator erzeugt via *WeasyPrint* ein leeres PDF, dessen Text unsichtbar (`color: transparent`), aber mit perfekten PDF/UA-1 Tags an den exakten physischen Koordinaten versehen ist.
3. Das optische Original-PDF wird via `pikepdf` als Vektor-Grafik unter diese unsichtbare Struktur gestempelt und als `/Artifact` deklariert.

## 3. Blackboard Pattern & Sensor Fusion

Die Klasse `SemanticOrchestrator` fungiert als Steuerzentrale:
1. **Map-Phase:** Alle registrierten Basis-Worker (Layout, Tabellen, Formeln, Fußnoten) werden parallel/sequenziell auf das Ziel-PDF angesetzt. Sie hinterlassen ihre Ergebnisse im temporären Job-Verzeichnis (dem "Blackboard").
2. **Reduce-Phase (Sensor Fusion):** Die Engine liest die JSON-Dateien. Sie verwebt hochpräzise Tabellen, komplexe Formeln und Signatur-Labels nahtlos mit dem Fließtext und entfernt dank Bounding-Box-Kollisionsprüfung redundanten Text-Müll. Nachgelagerte Worker (wie Translation oder Vision) reichern die fusionierten Daten weiter an.

## 4. Enterprise Error Contract & Graceful Degradation

KI-Modelle können abstürzen (z.B. durch GPU Out-Of-Memory). Um zu verhindern, dass die gesamte Pipeline stirbt, ist ein **Central Error Contract** implementiert. 
Stürzt ein Worker ab oder ist ein lokaler Dienst offline (Health-Check), fängt der Worker dies ab und schreibt ein standardisiertes `error.json` zurück an den Orchestrator. Das System führt eine *Graceful Degradation* (Rückfall auf Standardwerte) durch und die Konvertierung läuft stabil weiter.

## 5. Audit Trail Logging

Für den Einsatz in Konzernen und Behörden muss jede KI-Entscheidung nachvollziehbar sein. Der Orchestrator schreibt parallel zum fertigen PDF eine maschinenlesbare `pdfua.audit.json`. Diese enthält:
- Laufzeiten aller Worker auf die Millisekunde genau.
- Die detaillierten Error-Contracts (falls ein Worker degradiert ist).
- Die exakten Preflight-Diagnosen (Ghost-Fonts, fehlendes Embedding).
- Den kryptografischen Validierungs-Stempel der veraPDF-Endabnahme.

## 6. Telemetrie-freie Runtime-Isolation

Da das Tool "100% On-Premise" garantieren muss, injiziert der Orchestrator harte Umgebungsvariablen (`HF_HUB_OFFLINE=1`, `DISABLE_TELEMETRY=1`) in die Subprozesse der Worker. Dadurch wird garantiert, dass Bibliotheken wie PyTorch oder HuggingFace keinerlei Tracking-Daten oder Modell-Updates über das Internet anfordern.

## 7. Preflight & Defensive Sanitization

Gedruckte PDFs enthalten häufig *Type-3 Fonts*, die eine semantische Textextraktion unmöglich machen.
Das `PDFPreflightScanner`-Modul untersucht das Dokument **vor** der Verarbeitung. Findet es Defekte, erzwingt es die `needs_visual_reconstruction`-Strategie (Visual OCR Flattening).
Zusätzlich durchläuft der von der KI extrahierte Text die `repair.py` Facade, welche unsichtbare ASCII-Kontrollzeichen entfernt und Listen/Überschriften repariert, um veraPDF FATAL Errors (z.B. `.notdef` Glyphen) algorithmisch zu verhindern.
