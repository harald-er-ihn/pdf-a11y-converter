# 🏛️ System Architecture: PDF A11y Converter

Dieses Dokument beschreibt die architektonischen Designentscheidungen, Patterns und Datenflüsse des PDF A11y Converters. 

Das System wurde nach den Prinzipien der **Clean Architecture** entwickelt. Das oberste Paradigma bei der Entwicklung war: **Qualität, Isolation, Auditierbarkeit und deterministische Stabilität vor Komplexität.**

## 1. Clean Architecture & Plugin Discovery

Um Dependency-Hell zu verhindern, ist die Architektur strikt unterteilt:
- **Domain Layer (`src/domain/`)**: Enthält vertragliche Typisierungen (`SpatialDOM`) sowie die reinen Geschäftsregeln (Geometrie, Bipartite Matching, Layout Graphs, Constraint Solving). Keine Abhängigkeiten zu externen Frameworks.
- **Application Layer (`src/application/`)**: Der `SemanticOrchestrator` steuert den Datenfluss. Der `DOMTransformer` wendet die Domain-Regeln auf das SpatialDOM an.
- **Infrastructure Layer (`src/infrastructure/`)**: Implementiert die technischen Details (WeasyPrint, veraPDF Endabnahme).
- **Plugin Layer (`src/plugins/` & `workers/`)**: Verwaltet isolierte KI-Experten in eigenen Venvs, die dynamisch via `manifest.json` gefunden und koordiniert werden.

## 2. Das "Semantic Overlay" Pattern (Der Compiler-Ansatz)

Die klassische Erstellung von barrierefreien PDFs basiert auf HTML-to-PDF-Engines, die den Text neu setzen (Reflow). Das zerstört jedoch oft das Corporate Design. Dieses Projekt agiert als **Semantic Overlay Compiler**:
1. Extraktion millimetergenauer Koordinaten aus dem Original.
2. Generierung eines leeren PDFs via *WeasyPrint*, dessen Text unsichtbar (`color: transparent`), aber mit PDF/UA-1 Tags versehen ist.
3. Das optische Original-PDF wird als Vektorgrafik (`/Artifact`) in den Hintergrund gestempelt.

## 3. Topologische Graphen-Fusion & Sensor Fusion Pipeline

Das System geht weit über naive Bounding-Box Überlagerungen hinaus. Die Fusion von Layouts, Tabellen, Captions und Signaturen passiert in mehreren, streng überwachten Phasen:

### A. Coordinate Anti-Corruption Layer
Worker liefern unterschiedliche Koordinaten (Docling = Top-Left, PDF = Bottom-Left, YOLO = Pixel). Der `CoordinateAdapter` normalisiert *alle* Worker-Boxen per Fail-Fast-Contract in den PDF-Standard (Top-Left, 72 DPI), bevor sie das SpatialDOM berühren.

### B. Text-Aware Bipartite Matching
Eine rein geometrische Überlappungsprüfung (IoU) ist bei leichten OCR-Drifts unbrauchbar. Der `SpatialMatcher` nutzt eine gewichtete Fusion (Alpha * IoU + Beta * Levenshtein Text Similarity). Tabellen und Fragmente matchen dadurch selbst bei leicht verschobenen Bounding-Boxes zielsicher mit den Layout-Texten.

### C. Spatial Constraint Solving (Graceful Fallback)
Stürzt der High-End Layout-Worker ab, liefert der Fallback-Worker (Marker) oft nur einen gigantischen Text-Block für die ganze Seite. Wenn nun ein anderer Worker eine Tabelle mitten im Text findet, zerreißt der `SpatialConstraintSolver` den großen Textblock deterministisch. Er führt eine "räumliche Subtraktion" durch, um das kleinere Element passend einzubetten, ohne die angrenzenden Originaltexte zu vernichten.

### D. Topological Layout Graph Model & XY-Cut
Neue Elemente werden nicht mehr einfach an das DOM angehängt (was die Screenreader-Lesereihenfolge zerstören würde). Das Dokument wird in den `LayoutGraph` überführt. Knoten werden über Kanten wie `COLUMN_OF`, `ABOVE`, `CAPTION_OF` vernetzt. Abschließend sortiert ein deterministischer XY-Cut-Algorithmus alle Elemente in die perfekte, PDF/UA-konforme *Reading Order*.

## 4. Enterprise Error Contract & Locking

- **GPU-Locking:** Der `WorkerRunner` serialisiert Zugriffe auf die Grafikkarte thread-sicher, während CPU-Tasks hochparallel weiterlaufen.
- **Error Contracts:** Stürzt ein Worker ab (z.B. OOM-Error in PyTorch), schreibt er ein standardisiertes `error.json` an den Orchestrator. Das System degeneriert *graceful* und läuft mit Fallbacks weiter.

## 5. Audit Trail & Telemetrie-freie Isolation

Für den Einsatz in Konzernen und Behörden protokolliert die Engine eine maschinenlesbare `audit.json`. Diese enthält Laufzeiten, Degradations-Gründe, Preflight-Ergebnisse und das kryptografische veraPDF Endabnahme-Siegel. Harte Environment-Flags blocken PyTorch/HuggingFace Tracking ab und garantieren 100% On-Premise Compliance.

## 6. Telemetrie-freie Runtime-Isolation

Da das Tool "100% On-Premise" garantieren muss, injiziert der Orchestrator harte Umgebungsvariablen (`HF_HUB_OFFLINE=1`, `DISABLE_TELEMETRY=1`) in die Subprozesse der Worker. Dadurch wird garantiert, dass Bibliotheken wie PyTorch oder HuggingFace keinerlei Tracking-Daten oder Modell-Updates über das Internet anfordern.

## 7. Preflight & Defensive Sanitization

Gedruckte PDFs enthalten häufig *Type-3 Fonts*, die eine semantische Textextraktion unmöglich machen.
Das `PDFPreflightScanner`-Modul untersucht das Dokument **vor** der Verarbeitung. Findet es Defekte, erzwingt es die `needs_visual_reconstruction`-Strategie (Visual OCR Flattening).
Zusätzlich durchläuft der von der KI extrahierte Text die `repair.py` Facade, welche unsichtbare ASCII-Kontrollzeichen entfernt und Listen/Überschriften repariert, um veraPDF FATAL Errors (z.B. `.notdef` Glyphen) algorithmisch zu verhindern.

## 8. MCID-to-Text Mapping als dokumentbasiertes Signal

Für getaggte PDFs kann vorhandene Strukturinformation aus dem `/StructTreeRoot` mit sichtbarem Content-Stream-Text verbunden werden. Ziel ist zunächst ein reines Audit-/Signal-Artefakt, kein automatischer Eingriff in DOM, Repair oder Textkorrektur.

### Forschungsergebnis

PyMuPDF liefert zuverlässigen sichtbaren Layouttext, BBoxes und Lesereihenfolge-Signale, aber über `page.get_text("dict")` und `page.get_text("rawdict")` keine MCID- oder Tag-Felder. Für direktes MCID-to-Text-Mapping ist PyMuPDF daher nicht ausreichend, bleibt aber als Vergleichs- und Fallback-Quelle nützlich.

Der PDF-`/StructTreeRoot` liefert bei getaggten PDFs MCID-Referenzen inklusive Seitenbezug und Strukturkontext. Wichtig ist dabei nicht nur der innerste Tag, sondern der vollständige Strukturpfad mit Ancestor-Tags. Ein MCID-Kind kann z.B. direkt unter `Span` liegen, während der Pfad zusätzlich einen `H1`-Ancestor enthält.

Mit `pikepdf.parse_content_stream(...)` lassen sich marked-content-Bereiche (`BDC`, `BMC`, `EMC`) sowie Textoperatoren (`Tj`, `TJ`) und Fontwechsel (`Tf`) auswerten. Die Textdaten im Content Stream sind fontkodiert; die Unicode-Dekodierung erfolgt generisch über die `/ToUnicode`-CMap der jeweils aktiven Fontressource.

Diese Dekodierung basiert ausschließlich auf PDF-internen Signalen, nicht auf Wörterbüchern oder domänenspezifischen Ersetzungen.

### Geplante Signal-API

Das geplante Modul ist `src/infrastructure/pdf/mcid_text_extractor.py`.

Geplante öffentliche API: `extract_mcid_text_signals(pdf_path, output_path=None) -> dict`.

Das Ergebnis soll u.a. enthalten:

- Status (`success`, `skipped`, `error`)
- Seiten-, Font- und ToUnicode-Zusammenfassung
- Records pro `page`/`mcid`
- `struct_path`, `nearest_tag`, `has_heading_ancestor`
- dekodierten Text
- verwendete Fonts
- unbekannte Codes
- Confidence-Angabe

Bei ungetaggten PDFs oder fehlendem `/StructTreeRoot` wird sauber mit `status = skipped` und `reason = StructTreeRoot missing` beendet.

### Grenzen

Nicht alle Fonts besitzen `/ToUnicode`; CMaps können komplex sein; verschachteltes marked content muss stackbasiert verarbeitet werden. MCID-Text-Signale dürfen nicht blind sichtbaren Text, vorhandene Tags oder Überschriften ersetzen. Domänenspezifische Textkorrekturen wie globale Ersetzungen von Produkt- oder Projektnamen sind ausdrücklich zu vermeiden.

