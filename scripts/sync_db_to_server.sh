#!/usr/bin/env bash
set -Eeuo pipefail

# Sync the local Django SQLite database to the production VPS.
#
# Usage:
#   ./scripts/sync_db_to_server.sh
#   VPS_HOST=example.com VPS_USER=root ./scripts/sync_db_to_server.sh
#
# Authentication is intentionally delegated to SSH (prefer an SSH key).

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi
LOCAL_DB="${LOCAL_DB:-$PROJECT_ROOT/carfinder/db.sqlite3}"
VPS_HOST="${VPS_HOST:?VPS_HOST must be set in .env or the environment}"
VPS_USER="${VPS_USER:-root}"
REMOTE_DB="${REMOTE_DB:-/srv/torobche/carfinder/db.sqlite3}"
REMOTE_SERVICE="${REMOTE_SERVICE:-torobche}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)

die() {
  echo "Error: $*" >&2
  exit 1
}

command -v ssh >/dev/null || die "ssh is required"
command -v scp >/dev/null || die "scp is required"
[[ -f "$LOCAL_DB" ]] || die "local database not found: $LOCAL_DB"

# Validate the source database and make a consistent snapshot before touching
# the server. SQLite's backup API handles an app that is currently running.
local_snapshot="$(mktemp "${TMPDIR:-/tmp}/torobche-db.XXXXXX.sqlite3")"

python3 - "$LOCAL_DB" "$local_snapshot" <<'PY'
import sqlite3
import sys

source_path, snapshot_path = sys.argv[1:]
with sqlite3.connect(source_path) as connection:
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"SQLite integrity check failed: {result}")
with sqlite3.connect(source_path) as source, sqlite3.connect(snapshot_path) as snapshot:
    source.backup(snapshot)
with sqlite3.connect(snapshot_path) as connection:
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"SQLite snapshot integrity check failed: {result}")
PY

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
remote_tmp="${REMOTE_DB}.upload.${timestamp}"
remote_backup="${REMOTE_DB}.backup.${timestamp}"

echo "Checking SSH access to ${VPS_USER}@${VPS_HOST}..."
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" "test -f '$REMOTE_DB'"

echo "Creating remote backup: ${remote_backup}"
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" \
  "cp --preserve=all '$REMOTE_DB' '$remote_backup'"

cleanup() {
  rm -f "$local_snapshot"
  if [[ -n "${remote_tmp:-}" ]]; then
    ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" \
      "rm -f '$remote_tmp'" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Uploading a consistent snapshot of ${LOCAL_DB}..."
scp "${SSH_OPTS[@]}" "$local_snapshot" "${VPS_USER}@${VPS_HOST}:${remote_tmp}"

echo "Validating upload and switching database atomically..."
ssh "${SSH_OPTS[@]}" "${VPS_USER}@${VPS_HOST}" \
  "python3 - '$remote_tmp' '$REMOTE_DB' '$REMOTE_SERVICE' <<'PY'
import os
import shutil
import sqlite3
import subprocess
import sys

uploaded, destination, service = sys.argv[1:]
with sqlite3.connect(uploaded) as connection:
    result = connection.execute('PRAGMA integrity_check').fetchone()[0]
if result != 'ok':
    raise SystemExit(f'Uploaded SQLite integrity check failed: {result}')

shutil.copymode(destination, uploaded)
os.replace(uploaded, destination)
subprocess.run(['systemctl', 'restart', service], check=True)
PY"

trap - EXIT
echo "Database sync complete. Remote backup: ${remote_backup}"
