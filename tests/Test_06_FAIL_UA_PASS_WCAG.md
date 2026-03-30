# Test 06: PDF/UA Fail, WCAG Pass

Dieses Dokument soll an den strengen PDF-internen Vorschriften von PDF/UA-1 scheitern, aber die WCAG 2.2 Barrierefreiheits-Regeln bestehen.

## Der Metadaten-Test

WCAG 2.2 prüft, ob das Dokument eine logische Struktur hat, ob Tabellen Header haben und ob Alternativtexte existieren. All das ist hier gegeben.

PDF/UA-1 hat jedoch eine bürokratische Hürde: Die XMP-Metadaten des Dokuments müssen zwingend das Schema "PDF/UA Identification" (pdfuaid) enthalten. Fehlt dieser Stempel im PDF, ist das Dokument für Screenreader zwar perfekt lesbar (WCAG PASS), darf sich aber rechtlich nicht PDF/UA-1 nennen (UA FAIL).
