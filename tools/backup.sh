#!/usr/bin/env bash
set -Eeuo pipefail
LOCKFILE="/tmp/pdf-a11y-backup.lock"

exec 9>"$LOCKFILE"

if ! flock -n 9; then
    echo "Backup läuft bereits. Beende zweite Instanz."
    exit 1
fi
############################################
# KONFIGURATION
############################################

PROJECT_DIR="/media/harald/CloudSpace/pdf-a11y-converter"
RESTIC_REPOSITORY="/media/harald/CloudSpace/restic-backups"
RESTIC_PASSWORD_FILE="/home/harald/.restic-pw"
EXCLUDE_FILE="/media/harald/CloudSpace/pdf-a11y-converter/.gitignore"
LOG_FILE="/media/harald/CloudSpace/restic-backups/backup.log"
SCIEBO_TARGET="/media/harald/CloudSpace/Sciebo/Backups/pdf-a11y-restic"

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE

############################################
# VORBEREITUNG
############################################

mkdir -p "$RESTIC_REPOSITORY"
mkdir -p "$(dirname "$LOG_FILE")"

############################################
# LOGGING
############################################

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

trap 'log "❌ Fehler bei Zeile $LINENO"; exit 1' ERR

log "===== Restic Backup gestartet ====="

############################################
# BACKUP
############################################

restic backup "$PROJECT_DIR" \
    --exclude-file="$EXCLUDE_FILE" \
    --verbose

############################################
# RETENTION POLICY
############################################

log "Wende Aufräumregeln an..."

restic forget \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 6 \
    --prune

log "✅ Backup erfolgreich abgeschlossen"


log "Synchronisiere Repository nach Sciebo..."

rsync -a --delete "$RESTIC_REPOSITORY/" "$SCIEBO_TARGET/"

