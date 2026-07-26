#!/usr/bin/env bash
# Sends the once-a-day MOC email digest inside the running debt-criteria container.
# Install on the production host (NOT inside the container) via crontab, AFTER
# the hourly sync_crm_votes_cron.sh entry, timed for the end of the business day
# (e.g. 23:30 Europe/London so it covers the whole day's sync activity):
#   30 23 * * * /path/to/scripts/send_moc_digest_cron.sh >> /var/log/debt-criteria/moc_digest_cron.log 2>&1
set -euo pipefail

CONTAINER_NAME="debt-criteria"

docker exec "$CONTAINER_NAME" python manage.py send_moc_daily_digest
