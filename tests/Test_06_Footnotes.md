# Die Topologie von Dokumentengraphen

Die Extraktion von barrierefreien Strukturen aus unstrukturierten PDFs ist ein komplexes Problem der künstlichen Intelligenz[^1]. Anstatt einfache Heuristiken zu verwenden, transformieren moderne Ansätze das Dokument in einen Graphen[^2].

## Methodik

Knoten repräsentieren Textblöcke oder Bilder, während Kanten räumliche Beziehungen wie `ABOVE`, `BELOW` oder `COLUMN_OF` darstellen. Durch topologisches Sortieren[^3] kann die exakte Lesereihenfolge rekonstruiert werden.

Dies ist besonders wichtig, um die Vorschriften der Barrierefreien-Informationstechnik-Verordnung (BITV 2.0) im öffentlichen Sektor zu erfüllen.

[^1]: Vgl. Hutter, H. (2026): "Semantic Overlay Pattern in PDF/UA", Journal of Accessibility.
[^2]: Ein Graph besteht formal aus einer Menge von Knoten (Nodes) und Kanten (Edges).
[^3]: Die topologische Sortierung ist ein linearer Suchalgorithmus für gerichtete Graphen.
