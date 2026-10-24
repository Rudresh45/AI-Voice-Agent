#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "Usage: $0 /path/to/backup.dump" >&2; exit 2; fi
test -f "$1"
pg_restore --list "$1" >/dev/null
echo "Archive structure is readable. This is not a full restore test."
