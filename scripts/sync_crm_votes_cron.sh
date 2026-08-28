#!/usr/bin/env bash
# Runs the CRM vote summary sync inside the running debt-criteria container.
# Install on the production host (NOT inside the container) via crontab:
#   0 * * * * /path/to/scripts/sync_crm_votes_cron.sh >> /var/log/debt-criteria/crm_vote_sync_cron.log 2>&1
set -euo pipefail

CONTAINER_NAME="debt-criteria"

docker exec "$CONTAINER_NAME" python manage.py sync_creditor_vote_summaries \
  --log-file /app/logs/creditor_vote_sync.log
