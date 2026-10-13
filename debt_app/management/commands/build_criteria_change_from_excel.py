"""
Propose the database changes implied by the Excel Criteria markdown as DRAFT
criteria change requests.

    python manage.py build_criteria_change_from_excel --dry-run              # print proposals, write nothing
    python manage.py build_criteria_change_from_excel --user <username>      # create / refresh the drafts
    python manage.py build_criteria_change_from_excel --criteria-dir <dir>   # read markdown from elsewhere

Run the notes-only sync (seed_creditor_criteria) and seed_all_councils first so
new creditors and councils exist; this command only proposes changes to rows
that already exist. Drafts are never trialled or approved here: a manager
runs the trial and a second manager signs off on the Criteria Changes page.

One draft per group (creditor statuses, council statuses, dividends and
representatives, rule switches, HMRC equity rule). Re-running is safe: an
unchanged proposal is reported against the existing draft; a changed one
cancels that draft and creates a fresh one, and the difference is printed.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from debt_app.services.criteria_change_builder import build_proposals, render_report, sync_drafts


class Command(BaseCommand):
    help = "Create DRAFT criteria change requests from the Excel Criteria markdown (never applies them)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the proposals; create nothing.")
        parser.add_argument("--user", default=None, help="Username to record as the author of the drafts (required unless --dry-run).")
        parser.add_argument("--criteria-dir", default=None, help="Folder holding the markdown (default: <project>/Excel Criteria).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        user = None
        if not dry_run:
            if not options["user"]:
                raise CommandError("--user is required to create drafts (or pass --dry-run).")
            User = get_user_model()
            try:
                user = User.objects.get(username=options["user"])
            except User.DoesNotExist:
                raise CommandError(f"No user named {options['user']!r}.")

        ps = build_proposals(options["criteria_dir"])
        results = sync_drafts(ps, user=user, dry_run=dry_run, criteria_dir=options["criteria_dir"])
        self.stdout.write(render_report(ps, results))

        total = sum(len(r["proposals"]) for r in results)
        created = [r for r in results if r["action"] in ("created", "replaced")]
        if dry_run:
            self.stdout.write(self.style.WARNING(f"\nDry run: {total} proposed change(s); no draft written."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n{total} proposed change(s); {len(created)} draft(s) created or refreshed. "
                "Nothing has been applied: each draft still needs a trial and a second manager's approval."
            ))
