# scripts/

| Path | Purpose |
| --- | --- |
| `sync_crm_votes.bat` / `sync_crm_votes_cron.sh` | Scheduled CRM vote sync (hourly). Wraps `manage.py sync_creditor_vote_summaries`. |
| `send_moc_digest.bat` / `send_moc_digest_cron.sh` | Nightly MOC alert digest. Wraps `manage.py send_moc_daily_digest`. |
| `dev/` | Ad-hoc verification scripts — see `dev/README.md`. |
