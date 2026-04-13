#!/usr/bin/env bash
#
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
#

set -Eeuo pipefail

########################################
# Configuration
########################################

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKERS_DIR="${PROJECT_ROOT}/workers"
DEFAULT_PYTHON="python3"

# Worker-spezifische Runtime-Zuordnung (Strategy Pattern)
declare -A WORKER_PYTHON_MAP=(
#  ["formula_worker"]="python3.11"  hat nicht geklappt
)

########################################
# Logging
########################################

log_info()    { printf "\n\033[1;34m[INFO]\033[0m %s\n" "$1"; }
log_success() { printf "\033[1;32m[SUCCESS]\033[0m %s\n" "$1"; }
log_error()   { printf "\033[1;31m[ERROR]\033[0m %s\n" "$1" >&2; }

########################################
# Error Handling
########################################

on_error() {
  log_error "Fehler in Zeile ${BASH_LINENO[0]}. Script wird abgebrochen."
  exit 1
}

trap on_error ERR

########################################
# Python 3.11 Installation (Ubuntu/Debian)
########################################

ensure_python311_installed() {
  if command -v python3.11 >/dev/null 2>&1; then
    return
  fi

  log_info "Python 3.11 nicht gefunden. Installiere python3.11 und python3.11-venv..."

  if ! command -v apt-get >/dev/null 2>&1; then
    log_error "Automatische Installation nur für Debian/Ubuntu unterstützt."
    exit 1
  fi

  sudo apt update
  sudo apt install software-properties-common -y
  sudo add-apt-repository ppa:deadsnakes/ppa -y
  sudo apt update
  sudo apt install python3.11 python3.11-venv python3.11-distutils -y

  if ! command -v python3.11 >/dev/null 2>&1; then
    log_error "Python 3.11 Installation fehlgeschlagen."
    exit 1
  fi

  log_success "Python 3.11 erfolgreich installiert."
}

########################################
# Validation
########################################

if [[ ! -d "${WORKERS_DIR}" ]]; then
  log_error "Workers-Verzeichnis nicht gefunden: ${WORKERS_DIR}"
  exit 1
fi

command -v "${DEFAULT_PYTHON}" >/dev/null 2>&1 || {
  log_error "${DEFAULT_PYTHON} ist nicht installiert."
  exit 1
}

########################################
# Core Logic
########################################

for worker_path in "${WORKERS_DIR}"/*/; do
  worker_name="$(basename "${worker_path}")"

  # 🚀 FIX: 'common' ist eine Shared Library, kein Worker! Überspringen.
  if [[ "${worker_name}" == "common" || "${worker_name}" == "__pycache__" ]]; then
    continue
  fi

  log_info "Baue virtuelle Umgebung für: ${worker_name}"

  if [[ ! -f "${worker_path}/requirements.txt" ]]; then
    log_error "requirements.txt fehlt in ${worker_name}"
    exit 1
  fi

  # Interpreter bestimmen
  PYTHON_BIN="${WORKER_PYTHON_MAP[$worker_name]:-${DEFAULT_PYTHON}}"

  if [[ "${PYTHON_BIN}" == "python3.11" ]]; then
    ensure_python311_installed
  fi

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    log_error "Interpreter ${PYTHON_BIN} nicht verfügbar."
    exit 1
  fi

  pushd "${worker_path}" >/dev/null

  rm -rf venv
  "${PYTHON_BIN}" -m venv venv

  # shellcheck disable=SC1091
  source venv/bin/activate

  # 🚀 FIX: Upgrade pip, setuptools und wheel, um Compiler-Crashes (Maturin/Rust) auf Linux zu vermeiden
  python -m pip install --upgrade pip setuptools wheel -q

  if [[ -f "constraints.txt" ]]; then
    pip install -r requirements.txt -c constraints.txt
  else
    pip install -r requirements.txt
  fi

  deactivate
  popd >/dev/null

  log_success "Fertig: ${worker_name} (Interpreter: ${PYTHON_BIN})"
done

log_success "Alle Worker-venvs wurden erfolgreich neu aufgebaut."
