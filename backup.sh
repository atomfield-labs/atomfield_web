#!/bin/bash
# Copies the database, keeping one copy per weekday. Run from this folder.
# A failed copy leaves the last good one in place.
set -euo pipefail
copy="backups/nightly-$(date +%a).sql.gz"
docker compose exec -T db pg_dump -U postgres atomfield_db \
  | gzip > "$copy.tmp"
mv "$copy.tmp" "$copy"
