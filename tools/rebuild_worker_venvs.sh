#!/usr/bin/env bash
#
# PDF A11y Converter
# Copyright (C) 2026 Dr. Harald Hutter
# Licensed under the GNU General Public License v3 or later
#

set -Eeuo pipefail
export LC_ALL=C

########################################
# Configuration
########################################

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKERS_DIR="${PROJECT_ROOT}/workers"
DEFAULT_PYTHON="python3"

FORCE_REBUILD=false
PARALLEL_JOBS=1

# Worker-spezifische Runtime-Zuordnung (Strategy Pattern)
declare -A WORKER_PYTHON_MAP=(
# ["formula_worker"]="python3.11"
)

########################################
# Logging
########################################

log_info()    { printf "\n\033[1;34m[INFO]\033[0m %s\n" "$1"; }
log_success() { printf "\033[1;32m[SUCCESS]\033[0m %s\n" "$1"; }
log_warn()    { printf "\033[1;33m[WARN]\033[0m %s\n" "$1"; }
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
# CLI Arguments
########################################

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE_REBUILD=true
      shift
      ;;
    -j|--jobs)
      PARALLEL_JOBS="$2"
      shift 2
      ;;
    *)
      log_error "Unbekannter Parameter: $1"
      exit 1
      ;;
  esac
done

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
# Python 3.11 Installer (Ubuntu/Debian)
########################################

ensure_python311_installed() {

  if command -v python3.11 >/dev/null 2>&1; then
    return
  fi

  log_info "Installiere Python 3.11..."

  if ! command -v apt-get >/dev/null 2>&1; then
    log_error "Automatische Installation nur für Debian/Ubuntu unterstützt."
    exit 1
  fi

  sudo apt update
  sudo apt install software-properties-common -y
  sudo add-apt-repository ppa:deadsnakes/ppa -y
  sudo apt update
  sudo apt install python3.11 python3.11-venv python3.11-distutils -y

  command -v python3.11 >/dev/null 2>&1 || {
    log_error "Python 3.11 Installation fehlgeschlagen."
    exit 1
  }

  log_success "Python 3.11 installiert."
}

########################################
# Hash Helpers
########################################

calculate_hash() {

  local worker_path="$1"
  local python_bin="$2"

  local hash_input=""

  [[ -f "${worker_path}/requirements.txt" ]] \
    && hash_input+="$(cat "${worker_path}/requirements.txt")"

  [[ -f "${worker_path}/constraints.txt" ]] \
    && hash_input+="$(cat "${worker_path}/constraints.txt")"

  hash_input+="${python_bin}"

  echo -n "$hash_input" | sha256sum | cut -d' ' -f1
}

########################################
# Worker Builder
########################################

build_worker() {

  local worker_path="$1"
  local worker_name="$2"

  log_info "Prüfe Worker: ${worker_name}"

  if [[ ! -f "${worker_path}/requirements.txt" ]]; then
    log_error "requirements.txt fehlt in ${worker_name}"
    exit 1
  fi

  local PYTHON_BIN="${WORKER_PYTHON_MAP[$worker_name]:-${DEFAULT_PYTHON}}"

  if [[ "${PYTHON_BIN}" == "python3.11" ]]; then
    ensure_python311_installed
  fi

  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
    log_error "Interpreter ${PYTHON_BIN} nicht verfügbar."
    exit 1
  }

  local HASH_FILE="${worker_path}/venv/.build_hash"
  local CURRENT_HASH

  CURRENT_HASH=$(calculate_hash "${worker_path}" "${PYTHON_BIN}")

  if [[ "${FORCE_REBUILD}" == false && -f "${HASH_FILE}" ]]; then

    local OLD_HASH
    OLD_HASH=$(cat "${HASH_FILE}")

    if [[ "${OLD_HASH}" == "${CURRENT_HASH}" ]]; then
      log_success "${worker_name} → SKIPPED"
      return
    fi

  fi

  log_warn "${worker_name} → REBUILD"

  pushd "${worker_path}" >/dev/null

  rm -rf venv
  "${PYTHON_BIN}" -m venv venv

  # shellcheck disable=SC1091
  source venv/bin/activate

  python -m pip install --upgrade pip setuptools wheel -q

  if [[ -f "constraints.txt" ]]; then
    pip install -r requirements.txt -c constraints.txt
  else
    pip install -r requirements.txt
  fi

  echo "${CURRENT_HASH}" > venv/.build_hash

  deactivate
  popd >/dev/null

  log_success "${worker_name} → BUILT"
}

########################################
# Worker Discovery
########################################

workers=()

for worker_path in "${WORKERS_DIR}"/*/; do

  worker_name="$(basename "${worker_path}")"

  if [[ "${worker_name}" == "common" || "${worker_name}" == "__pycache__" ]]; then
    continue
  fi

  workers+=("${worker_path}")

done

########################################
# Parallel Runner
########################################

run_parallel_build() {

  # shellcheck disable=SC2016
  printf "%s\n" "${workers[@]}" | \
    xargs -P "${PARALLEL_JOBS}" -I{} bash -c '
      worker_path="$1"
      worker_name=$(basename "$worker_path")
      build_worker "$worker_path" "$worker_name"
    ' _ {}
}

########################################
# Execution
########################################

log_info "Starte Worker-Buildsystem"
log_info "Force-Rebuild: ${FORCE_REBUILD}"
log_info "Parallel Jobs: ${PARALLEL_JOBS}"

if [[ "${PARALLEL_JOBS}" -gt 1 ]]; then

  export WORKERS_DIR DEFAULT_PYTHON FORCE_REBUILD
  export -f build_worker calculate_hash ensure_python311_installed \
            log_info log_success log_warn log_error

  run_parallel_build

else

  for worker_path in "${workers[@]}"; do

    worker_name="$(basename "${worker_path}")"
    build_worker "${worker_path}" "${worker_name}"

  done

fi

log_success "Alle Worker-Venvs sind aktuell."
