#!/usr/bin/env bash
set -euo pipefail
: "${RESTORE_DATABASE_URL:?Set RESTORE_DATABASE_URL to an isolated test database}"
if [[ $# -ne 1 ]]; then echo "Usage: $0 /path/to/decrypted-backup.dump" >&2; exit 2; fi
test -f "$1"
pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" "$1"
echo "Restore command completed. Run integrity and tenant-isolation tests next."
