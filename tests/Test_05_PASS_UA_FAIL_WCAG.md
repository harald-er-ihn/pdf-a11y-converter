# Test 05: PDF/UA Pass, WCAG Fail

Dieses Dokument soll die technische PDF/UA-1 Prüfung bestehen, aber an den strengen visuellen WCAG 2.2 Richtlinien scheitern.

## Der Farbkontrast-Test

PDF/UA-1 interessiert sich nicht für Farben. Solange der Text als Textlayer vorhanden und als `<p>` getaggt ist, ist PDF/UA glücklich. 

WCAG 2.2 (Kriterium 1.4.3 Contrast Minimum) fordert jedoch ein Kontrastverhältnis von mindestens 4.5:1. Wenn wir hellgrauen Text auf weißem Grund ausgeben, scheitert die WCAG-Prüfung krachend, während PDF/UA weiterhin auf "PASS" steht.

Da unser Converter normalerweise den unsichtbaren Modus (3 Tr) nutzt, entgeht er diesem Fehler. Ohne den Trick schlägt WCAG sofort Alarm.
