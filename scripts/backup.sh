#!/bin/sh
# Back up the database to backups/<timestamp>.dump and keep the newest 14.
#   scripts/backup.sh                 local Postgres (database research_scout)
#   scripts/backup.sh --compose       the docker compose db service
# Restore: pg_restore --clean --if-exists -d research_scout backups/<file>.dump
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/$(date +%Y%m%d-%H%M%S).dump"
if [ "${1:-}" = "--compose" ]; then
  docker compose exec -T db pg_dump -U scout -Fc research_scout > "$out"
else
  pg_dump -Fc research_scout -f "$out"
fi
ls -1t backups/*.dump | tail -n +15 | xargs rm -f
echo "saved $out"
