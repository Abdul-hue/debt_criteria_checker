"""
Record the CURRENT live managed criteria as a numbered CriteriaVersion, so a
later rollback can return to exactly this state.

    python manage.py record_criteria_baseline --note "Before the October 2026 workbook update"
    python manage.py record_criteria_baseline --note "..." --created-by <username>

Why: approve_and_apply() snapshots the state AFTER each approved change. If
live criteria were edited outside the workflow since the last version (the
live fingerprint no longer matches it), nothing holds the pre-change state and
"roll back to the previous version" would also undo those edits. Recording a
baseline first closes that gap. Does nothing if the live state already matches
the latest version. Never changes criteria.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from debt_app.models import CriteriaVersion
from debt_app.services import criteria_versioning as cv


def record_baseline(note, user=None):
    """Create the baseline version and return it, or return None when the live
    criteria already match the latest version (nothing to record)."""
    with transaction.atomic():
        snap = cv.snapshot_managed_criteria()
        fp = cv.fingerprint(snap)
        latest = CriteriaVersion.objects.select_for_update().order_by("-number").first()
        if latest is not None and latest.fingerprint == fp:
            return None
        return CriteriaVersion.objects.create(
            number=(latest.number + 1) if latest else 1,
            created_by=user,
            note=note[:255],
            snapshot=snap,
            fingerprint=fp,
            code_version=cv.get_code_version(),
        )


class Command(BaseCommand):
    help = "Record the current live managed criteria as a numbered version (rollback point). Changes no criteria."

    def add_arguments(self, parser):
        parser.add_argument("--note", required=True, help="Why this baseline is being recorded.")
        parser.add_argument("--created-by", default=None, help="Username to record against the version (optional).")

    def handle(self, *args, **options):
        user = None
        if options["created_by"]:
            try:
                user = get_user_model().objects.get(username=options["created_by"])
            except get_user_model().DoesNotExist:
                raise CommandError(f"No user named {options['created_by']!r}.")
        version = record_baseline(options["note"], user)
        if version is None:
            latest = CriteriaVersion.objects.order_by("-number").first()
            self.stdout.write(self.style.SUCCESS(
                f"Live criteria already match {latest.label} ({latest.fingerprint[:12]}); nothing recorded."
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Recorded {version.label} ({version.fingerprint[:12]}): {version.note}"
        ))
