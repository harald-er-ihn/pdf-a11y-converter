---
classoption: twocolumn
geometry: margin=2cm
---

# Zukünftige Herausforderungen der Sensor Fusion

Die Kombination mehrerer KI-Modelle zur Analyse von Dokumentenstrukturen wird als *Sensor Fusion* bezeichnet. 

In herkömmlichen Systemen führt die Überlagerung von Tabellendaten und Layout-Text oft zu Zerstörungen in der Lese-Reihenfolge (Reading Order). Unser System nutzt einen bipartiten Matching-Algorithmus, um Koordinaten aus unterschiedlichen KI-Workern (Docling, YOLO, Marker) in einem topologischen Graphen zu verschmelzen.

## Der XY-Cut Algorithmus

Um die strikten Anforderungen der Barrierefreiheit (PDF/UA-1) zu erfüllen, muss der Textfluss deterministisch sortiert werden. Der XY-Cut Algorithmus projiziert die Bounding Boxes auf die X- und Y-Achse, findet Lücken (Gaps) und schneidet das Dokument iterativ in Blöcke und Spalten.

Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. 

Durch das zweispaltige Layout muss der `column_worker` beweisen, dass er die Lücke in der Mitte des Blattes über sein X-Histogramm zuverlässig erkennt und den Textfluss von links-oben nach links-unten und erst dann nach rechts-oben leitet.
