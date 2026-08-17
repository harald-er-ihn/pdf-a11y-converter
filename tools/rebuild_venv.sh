#!/usr/bin/env bash
# PDF A11y Converter
# Erstellt das Venv für das Hauptprogramm neu und installiert Dev-Abhängigkeiten

set -euo pipefail

# Projekt-Root bestimmen: tools/.. 
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/requirements-dev.txt"

echo "🚀 Starte Rebuild des Hauptprogramm-Venvs..."
echo

if [ ! -f "$REQ_FILE" ]; then
    echo "❌ requirements-dev.txt nicht gefunden:"
    echo "   $REQ_FILE"
    exit 1
fi

# Python bestimmen
if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "❌ Kein Python gefunden. Bitte Python >= 3.12 installieren."
    exit 1
fi

PY_VERSION="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "🐍 Verwende Python: $PYTHON_BIN ($PY_VERSION)"

# Mindestversion prüfen
$PYTHON_BIN - <<'PY'
import sys
if sys.version_info < (3, 12):
    print("❌ Python >= 3.12 erforderlich.")
    print(f"   Gefunden: {sys.version}")
    sys.exit(1)
PY

# Altes Venv entfernen, falls vorhanden
if [ -d "$VENV_DIR" ]; then
    echo "🗑️  Entferne bestehendes Venv:"
    echo "   $VENV_DIR"
    rm -rf "$VENV_DIR"
fi

# Neues Venv erstellen
echo "📦 Erstelle neues Venv:"
echo "   $VENV_DIR"
$PYTHON_BIN -m venv "$VENV_DIR"

# Python im Venv bestimmen
VENV_PY="$VENV_DIR/bin/python"

# Basis-Pakete aktualisieren
echo "⬆️  Aktualisiere pip, setuptools und wheel..."
"$VENV_PY" -m pip install --upgrade pip setuptools wheel -q

# Dev-Abhängigkeiten installieren
echo "📥 Installiere Hauptprogramm + Dev-Abhängigkeiten..."
"$VENV_PY" -m pip install -r "$REQ_FILE"

echo
echo "✅ Hauptprogramm-Venv wurde erfolgreich eingerichtet!"
echo
echo "Aktivieren mit:"
echo "   source .venv/bin/activate"
