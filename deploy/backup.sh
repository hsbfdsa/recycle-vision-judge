#!/usr/bin/env bash
# 판정 기록 DB 백업. 하루 한 번 cron으로 돌리고 7일치만 남긴다.
#   등록:  crontab -e  →  10 4 * * * /home/ubuntu/recycle-vision-judge/deploy/backup.sh >> /home/ubuntu/backup.log 2>&1
#   복구:  gunzip -c ~/backups/rescan-날짜.sql.gz | docker compose exec -T db psql -U rescan -d rescan
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ~/backups
file=~/backups/rescan-$(date +%F).sql.gz
docker compose exec -T db pg_dump -U rescan -d rescan | gzip > "$file"
find ~/backups -name 'rescan-*.sql.gz' -mtime +7 -delete
echo "$(date '+%F %T') backup ok: $file ($(du -h "$file" | cut -f1))"
