# Systemarchitektur und Evaluierung

Das folgende Diagramm zeigt die Architektur des PDF A11y Converters. Die Caption-Erkennung muss das Wort "Abbildung" oder "Figure" unter dem Objekt identifizieren und topologisch verknüpfen.

![Systemarchitektur des Converters](static/img/architecture_graph.svg)

**Abbildung 1: Architektur-Übersicht der Clean Architecture Pipeline.**

## Ergebnisse der Validierung

Die nachfolgende Tabelle listet die Erfolgsquoten der einzelnen Worker auf.

| Worker | Erfolgsquote |
|--------|--------------|
| Layout | 99.4%        |
| Table  | 98.1%        |

**Tabelle 1: Benchmark-Ergebnisse der KI-Worker im Q1 2026.**

Die Heuristik muss erkennen, dass der Text direkt unter der Tabelle eine Beschriftung ist und die Kante `CAPTION_OF` im Layout Graph erzeugen.
