#!/bin/sh
# Usage: backup.sh /absolute/backup-directory [retention-days]
# Run on the Docker host. Stop ALL app writers; external DB server stays running.
set -eu
umask 077
DEPLOY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_CONTAINER=${APP_CONTAINER:-heritagekitchen}
BACKUP_DIR=${1:?Usage: backup.sh /absolute/backup-directory [retention-days]}
RETENTION_DAYS=${2:-30}
# Serialize the stop/start window, not just the archive operation.
exec 9>"$DEPLOY_DIR/.backup-wrapper.lock"
flock -n 9 || { echo 'Backup already running' >&2; exit 1; }
RUNNING=$(docker inspect --format '{{.State.Running}}' "$APP_CONTAINER")
# Resolve actual bind mounts before stopping the app; never use checkout data.
CONTAINER_DATABASE_URL=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$APP_CONTAINER" | sed -n 's/^DATABASE_URL=//p')
CONTAINER_MOUNTS=$(docker inspect --format '{{json .Mounts}}' "$APP_CONTAINER")
export CONTAINER_DATABASE_URL CONTAINER_MOUNTS
SOURCES=$(python3 "$DEPLOY_DIR/backup_mounts.py")
DATABASE_URL=$(printf '%s\n' "$SOURCES" | sed -n '1p')
IMAGES_DIR=$(printf '%s\n' "$SOURCES" | sed -n '2p')
unset CONTAINER_DATABASE_URL CONTAINER_MOUNTS SOURCES
export DATABASE_URL
restart_app() {
    if [ "$RUNNING" = true ]; then docker start "$APP_CONTAINER" >/dev/null; fi
}
trap restart_app EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$RUNNING" = true ]; then docker stop --time 60 "$APP_CONTAINER" >/dev/null; fi
python3 "$DEPLOY_DIR/backup.py" --images-dir "$IMAGES_DIR" backup --backup-dir "$BACKUP_DIR" --retention-days "$RETENTION_DAYS" --writers-stopped
