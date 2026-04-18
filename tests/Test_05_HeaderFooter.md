---
geometry: margin=2.5cm
header-includes:
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhead[L]{Unternehmensrichtlinie 2026}
  - \fancyhead[R]{\today}
  - \fancyfoot[C]{Seite \thepage}
---

# Qualitätsmanagement-Handbuch

Dieses Dokument testet den `header_footer_worker`. Die Kopfzeile enthält den Titel und das Datum, die Fußzeile die Seitenzahl. Diese Elemente müssen vom Algorithmus als `/Artifact` getaggt werden, damit Screenreader sie nicht auf jeder Seite erneut vorlesen.

## Abschnitt A: Auditierung
Die Auditierung erfolgt jährlich. Dabei werden alle Prozesse auf Konformität mit der ISO 9001 geprüft. 

\newpage

## Abschnitt B: Maßnahmenplanung
Auf dieser zweiten Seite sehen wir erneut die Kopf- und Fußzeilen. Der Algorithmus muss erkennen, dass diese Texte auf derselben Y-Koordinate wiederkehren und sie aus dem semantischen DOM-Baum herausschneiden.

Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt.

\newpage

## Abschnitt C: Fazit
Seite 3 bestätigt die Frequenzanalyse des Workers. Texte, die in den äußeren 15% des Randes auf mehr als 20% der Seiten vorkommen, gelten sicher als Artefakt.
