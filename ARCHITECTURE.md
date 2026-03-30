# 🏛️ System Architecture: PDF A11y Converter

Dieses Dokument beschreibt die architektonischen Designentscheidungen, Patterns und Datenflüsse des PDF A11y Converters. 

Das oberste Paradigma bei der Entwicklung war: **Qualität, Isolation und Stabilität vor Komplexität.**

## 1. Das "Semantic Overlay" Pattern (Generator)

Die klassische Erstellung von barrierefreien PDFs basiert auf HTML-to-PDF-Engines, die den Text neu setzen (Reflow). Das zerstört jedoch oft das originäre Corporate Design. Dieses Projekt geht einen völlig anderen Weg:

1. Die Worker extrahieren millimetergenaue Koordinaten (Bounding Boxes) aller Elemente aus dem Original-PDF.
2. `generator.py` generiert via *WeasyPrint* ein leeres PDF, dessen Text unsichtbar (`color: transparent`), aber mit perfekten PDF/UA-1 Tags (H1, P, Table) an den exakten physischen Koordinaten versehen ist.
3. Das optische Original-PDF wird via `pikepdf` als Vektor-Grafik (`/XObject`) unter diese unsichtbare Struktur gestempelt und als `/Artifact` deklariert (damit der Screenreader es ignoriert).

*Das Ergebnis:* Ein optisch 1:1 identisches Dokument (Visual Fidelity) mit perfekter, unsichtbarer Barrierefreiheit im Vordergrund.

## 2. Venv-Worker-Isolation (Dependency Hell Prevention)

Moderne KI-Modelle (wie *Docling*, *Nougat*, *BLIP* oder *GROBID*) erfordern hochspezifische und oft inkompatible Versionen von PyTorch, CUDA oder PDF-Parsern (`pypdfium2`). Ein monolithisches Projekt würde sofort unter Versionskonflikten zusammenbrechen.

**Die Lösung:**
Jeder "Experte" lebt als isoliertes Skript in einem Unterordner von `workers/` mit einem eigenen, autonomen `venv`.
Die Hauptanwendung (Commander) ruft diese Worker über `subprocess` auf. 
*Vorteil:* Fällt ein Worker durch einen Out-Of-Memory-Error aus, stürzt die Hauptanwendung nicht ab (Fail-Fast-Prinzip). Das System bleibt robust.

## 3. Blackboard Pattern & Sensor Fusion (`engine.py`)

Die Klasse `SemanticOrchestrator` fungiert als Steuerzentrale:
1. **Map-Phase:** Alle Worker (Layout, Tabellen, Formeln, Fußnoten via Grobid) werden auf das Ziel-PDF angesetzt. Sie hinterlassen ihre Ergebnisse im temporären Job-Verzeichnis (dem "Blackboard").
2. **Reduce-Phase (Sensor Fusion):** Die Engine liest die JSON-Dateien. Sie verwebt hochpräzise Tabellen (von `pdfplumber`), komplexe Formeln (von `nougat`) und Fußnoten (von `grobid`) nahtlos mit dem Fließtext (von `docling`) und entfernt dank Bounding-Box-Kollisionsprüfung redundanten Text-Müll.
3. **Translation-Chain:** Bildbeschreibungen (von BLIP) und Signatur-Labels (von YOLO) werden auf dem Blackboard gesammelt und in einem Rutsch durch das `NLLB-200` Modell in die Zielsprache des PDF-Dokuments übersetzt (z.B. "Signature" -> "Unterschrift").

## 4. Preflight & Strategy Pattern (`pdf_diagnostics.py`)

Gedruckte PDFs (z.B. aus LaTeX oder Cairo) enthalten häufig *Type-3 Fonts* oder nicht eingebettete Schriften. Diese machen eine semantische Textextraktion unmöglich und verletzen PDF/UA-1 Normen (selbst im Hintergrund als Artefakt).

Das `PDFPreflightScanner`-Modul untersucht das Dokument **vor** der Verarbeitung. Findet es strukturelle Defekte, erzwingt es die `needs_visual_reconstruction`-Strategie:
- Den KI-Workern wird das Flag `--force-ocr` übergeben. Der unbrauchbare PDF-Textlayer wird ignoriert, die KI liest das Dokument rein visuell.
- Der Generator wendet **Flattening** an: Das Original-PDF wird in hochauflösende Bilder (300 DPI) gerastert, um die korrupten Schriften restlos (Ghost-Font Prevention) zu vernichten, bevor es in den Hintergrund gestempelt wird.

## 5. Der Datenvertrag: Das Spatial DOM (SDOM)

Um die Ergebnisse der Worker zu standardisieren, wurde ein JSON-basierter Vertrag etabliert. Alle Worker müssen ihre Ergebnisse in folgendem Format auf dem Blackboard ablegen:

```json
{
  "pages":[
    {
      "page_num": 1,
      "width": 595.0,
      "height": 842.0,
      "elements":[
        {
          "type": "p",
          "text": "Strukturierter Fließtext",
          "bbox":[50.0, 100.0, 500.0, 150.0],
          "html": "Optionales Feld für komplexe Tabellen"
        }
      ]
    }
  ],
  "images": {
    "image_0.png": "/tmp/path/to/extracted/image.png"
  }
}
```

## 6. Defensive Programming & Sanitization (repair.py)

Die Output-Daten von KI-Modellen sind inhärent unvorhersehbar. Um die strengen Validierungsregeln von veraPDF zu bestehen, durchläuft der extrahierte Text die `repair.py` Facade:

1. **Kontrollzeichen-Sanitisierung:** Entfernung von unsichtbaren ASCII-Zeichen (verhindert veraPDF FAIL 7.21.8 - `.notdef` Glyphen).
2. **Listen-Reparatur:** Reparatur von "Loose Lists" und leeren Listenfragmenten (behebt veraPDF FAIL 7.2-20). WeasyPrint wird gezwungen, saubere `<ol>`/`<ul>` Strukturen ohne fehlerhafte `<p>`-Injektionen aufzubauen.
3. **Überschriften-Hierarchie:** Erzwingung einer lückenlosen Tag-Hierarchie (H1 -> H2 -> H3). Sprünge (z.B. H1 direkt zu H3) werden algorithmisch geglättet (behebt veraPDF FAIL 7.4.2-1).

Nur durch diese hochdefensive Architektur können wir den Anspruch einer 100%igen maschinellen PDF/UA-1 Endabnahme garantieren.
