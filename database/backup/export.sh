#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?Set DATABASE_URL securely}"
: "${BACKUP_DIR:=./backup-output}"
mkdir -p "$BACKUP_DIR"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/voice-platform-$STAMP.dump"
pg_dump "$DATABASE_URL" --format=custom --no-owner --file="$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "Created local dump: $OUT"
echo "Encrypt and upload to independent private storage before considering backup complete."
