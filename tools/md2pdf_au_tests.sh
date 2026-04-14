#!/usr/bin/env bash
# PDF A11y Converter Test-Suite
# Strikte Fehlerbehandlung und Live-Ausgabe

set -euo pipefail

PROJECT_DIR="/media/harald/CloudSpace/pdf-a11y-converter"
LOGFILE="/home/harald/Dokumente/PDF-A11y-Converter/md2pdf_au-tests.log.txt"

cd "$PROJECT_DIR" || { echo "❌ Projektverzeichnis nicht gefunden."; exit 1; }

# Venv aktivieren (WICHTIG für lokale Tests)
source venv/bin/activate || { echo "❌ Venv konnte nicht aktiviert werden."; exit 1; }

echo "" > "$LOGFILE"

echo -e "\033[1;36m====================================================\033[0m" | tee -a "$LOGFILE"
echo -e "\033[1;36m  🚀 Starte Massen-Konvertierung (PDF/UA-1 Audit)   \033[0m" | tee -a "$LOGFILE"
echo -e "\033[1;36m====================================================\033[0m" | tee -a "$LOGFILE"

# Vorherige Test-Outputs löschen
#find tests/ -type f -name "*_pdfua.pdf" -delete
find tests/ -type f -name "*.pdf" -delete
find tests/ -type f -name "*_debug.html" -delete
find tests/ -type f -name "*.json" -delete



confirm="Y"
read -r -p "Continue? (Y/N): " confirm && [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]] || exit 1


# Alle Original-PDFs erstellen aus den md-Daten
for f in tests/Test_*.md; do     
	echo "======================================";
	echo "Generiere PDF aus $f";
    python tools/generate_test_pdf.py "$f";
done



# Alle Original-PDFs durchlaufen
for file in tests/*.pdf; do
    echo -e "\n\033[1;33m▶▶▶ VERARBEITE: $(basename "$file") \033[0m" | tee -a "$LOGFILE"
    
    # stdout und stderr werden zusammengeführt und via tee ins log UND auf den Screen geschrieben
    if python cli.py "$file" --visualscreenreader 2>&1 | tee -a "$LOGFILE"; then
        echo -e "\033[1;32m✅ ERFOLG: $(basename "$file")\033[0m" | tee -a "$LOGFILE"
    else
        echo -e "\033[1;31m❌ FEHLER: $(basename "$file")\033[0m" | tee -a "$LOGFILE"
    fi
done

echo -e "\n\033[1;36m🎉 Alle Dateien abgearbeitet! Log gespeichert unter:\033[0m"
echo "$LOGFILE"
