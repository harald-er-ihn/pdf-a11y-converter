#!/usr/bin/env bash
# PDF A11y Converter
# Code Audit Skript (Ruff, Djlint, Shellcheck & Pylint)

set -euo pipefail

PROJECT_DIR="/media/harald/CloudSpace/pdf-a11y-converter"
export PYTHONPATH=$PROJECT_DIR
TMP_ROOT="/home/harald/Downloads"
LOGFILE="/home/harald/Dokumente/PDF-A11y-Converter/code_audit.log.txt"
rm "$LOGFILE"
touch "$LOGFILE"

cd "$PROJECT_DIR" || { echo "❌ Projektverzeichnis nicht gefunden."; exit 1; }
mkdir -p "$TMP_ROOT"

echo -e "\n🚀 Starte venv..."| tee -a "$LOGFILE"
if source venv/bin/activate; then
    echo "✅ venv erfolgreich aktiviert!"| tee -a "$LOGFILE"
else
    echo "⚠️ Fehler beim Starten des venvs."| tee -a "$LOGFILE"
    exit 1
fi

#echo -e "\n🚀 Starte djlint..."| tee -a "$LOGFILE"
#if djlint . --reformat --quiet; then
#    echo "✅ djlint erfolgreich abgeschlossen!"| tee -a "$LOGFILE"
#else
#    echo "⚠️ Fehler bei djlint."| tee -a "$LOGFILE"
#fi

# Validierungen
python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"| tee -a "$LOGFILE"
jq . config/config.json | tee -a "$LOGFILE"
#jq . config/nllb_mapping.json | tee -a "$LOGFILE"
shellcheck -x ./tools/*.sh| tee -a "$LOGFILE"

echo -e "\n🔍 Starte Code-Formatter (Ruff)..."| tee -a "$LOGFILE"
ruff check . --fix| tee -a "$LOGFILE"
ruff format .| tee -a "$LOGFILE"

echo -e "\n🔍 Starte Qualitätsprüfung (Pylint)..."| tee -a "$LOGFILE"

confirm="Y"
read -r -p "Continue? (Y/N): " confirm && [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]] || exit 1


# Finde alle .py Dateien (ohne venvs) und übergebe sie an Pylint
find . -type f -name "*.py" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/build/*" \
    -not -path "*/dist/*" \
    -not -path "*/.ruff_cache/*"  -exec pylint {} +| tee -a "$LOGFILE"
# Finde alle .py Dateien (ohne venvs) und übergebe sie an Radon
find . -type f -name "*.py" \
    -not -path "*/venv/*" \
    -not -path "*/.venv/*" \
    -not -path "*/build/*" \
    -not -path "*/dist/*" \
    -not -path "*/.ruff_cache/*"  -exec radon cc -s {} +| tee -a "$LOGFILE"
