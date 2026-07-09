import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from debt_app.models import CrmSyncRun
from debt_app.services.crm_vote_sync import run_crm_vote_sync


class Command(BaseCommand):
    help = "Sync CRM vote summaries to CreditorVoteSummary model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be changed without writing to the database.",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default=os.path.join(settings.BASE_DIR, "creditor_vote_sync.log"),
            help="Path to the log file for audit purposes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        log_file = options["log_file"]

        run = CrmSyncRun.objects.create(trigger_source="CLI", dry_run=dry_run)

        try:
            run_crm_vote_sync(run=run, dry_run=dry_run, log_file=log_file)

            run.status = "SUCCESS"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])

            self.stdout.write(self.style.SUCCESS("Sync completed successfully!"))

        except Exception as e:
            run.status = "FAILED"
            run.finished_at = timezone.now()
            run.error_message = str(e)
            run.save(update_fields=["status", "finished_at", "error_message"])

            self.stderr.write(self.style.ERROR(f"Error during sync: {e}"))
            raise
