# Richtlinie zur digitalen Barrierefreiheit (PDF/UA)

## 1. Einleitung und Zielsetzung
Die Umsetzung der digitalen Barrierefreiheit ist nicht nur eine gesetzliche Vorgabe, sondern auch eine gesellschaftliche Verpflichtung. Dieser Leitfaden definiert die technischen und redaktionellen Anforderungen zur Erstellung konformer Dokumente.

Das Kernziel ist es, sicherzustellen, dass assistive Technologien (wie Screenreader) Dokumente in einer logischen Lesereihenfolge (Reading Order) interpretieren können.

### 1.1 Geltungsbereich
Diese Richtlinie gilt für alle Abteilungen, Fachbereiche und externe Dienstleister. Sie ist bindend für:
- Interne Memos und Arbeitsanweisungen
- Öffentlich zugängliche Berichte
- Formulare und interaktive Dokumente

## 2. Technische Anforderungen an das Spatial DOM

Das `SpatialDOM` ist der zentrale Datenvertrag des PDF A11y Converters. Es verlangt eine millimetergenaue Ausrichtung von Bounding Boxes.

### 2.1 Visuelle Ebene vs. Semantische Ebene
Wir folgen strikt dem *Semantic Overlay Pattern*:
1. Das Originaldokument wird als Vektorgrafik im Hintergrund gerendert (`/Artifact`).
2. Eine unsichtbare Textebene wird pixelgenau darübergelegt.
3. Struktur-Tags (`H1`, `P`, `Table`) ordnen den unsichtbaren Text.

### Checkliste zur Validierung
* [ ] Preflight-Check durchgeführt
* [ ] Type-3 Fonts entfernt oder vektorisiert
* [ ] veraPDF Profil `PDFUA-1` bestanden

## 3. Hintergrundwissen
Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. (Dieser Text simuliert einen längeren Fließtext, um den Seitenumbruch in Pandoc zu provozieren). 

Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum.
