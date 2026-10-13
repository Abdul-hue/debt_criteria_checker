"""
Regenerate the markdown files in ``Excel Criteria/`` from the criteria workbook.

    python manage.py export_excel_criteria --xlsx "path/to/TIP CRITERIA & VOTING HISTORY.xlsx"
    python manage.py export_excel_criteria --xlsx ... --dry-run        # report only, write nothing
    python manage.py export_excel_criteria --xlsx ... --out some/dir   # write elsewhere (e.g. to diff)
    python manage.py export_excel_criteria --xlsx ... --drop-missing   # do not keep hand-added rows
    python manage.py export_excel_criteria --xlsx ... --keep-evolve    # keep the EVOLVE representative section

This touches markdown files only. Nothing is written to the database; the
seed commands and the criteria change workflow do that, separately, after the
regenerated files have been reviewed in git.

The prose sheets (TIG / Watch / TIX Criteria) are hand-maintained markdown and
are not regenerated; the command reminds you to check them.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from debt_app.services.excel_criteria import export_workbook


class Command(BaseCommand):
    help = "Regenerate the Excel Criteria markdown files from the criteria workbook (no database writes)."

    def add_arguments(self, parser):
        parser.add_argument("--xlsx", required=True, help="Path to the TIP CRITERIA & VOTING HISTORY workbook")
        parser.add_argument("--out", default=None, help="Output folder (default: <project>/Excel Criteria)")
        parser.add_argument("--dry-run", action="store_true", help="Print the report but write nothing")
        parser.add_argument("--drop-missing", action="store_true",
                            help="Do not keep rows that exist in the current markdown but not in the workbook")
        parser.add_argument("--keep-evolve", action="store_true",
                            help="Keep the EVOLVE section of Which Representative (dropped by default: Evolve was retired 2026-10-12)")

    def handle(self, *args, **options):
        xlsx = Path(options["xlsx"])
        if not xlsx.exists():
            raise CommandError(f"Workbook not found: {xlsx}")
        out_dir = Path(options["out"]) if options["out"] else Path(settings.BASE_DIR) / "Excel Criteria"

        report, outputs = export_workbook(
            xlsx, out_dir,
            drop_missing=options["drop_missing"],
            keep_evolve=options["keep_evolve"],
            write=not options["dry_run"],
        )

        self.stdout.write(report.as_text())
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"\nDry run: nothing written. Would write {len(outputs)} file(s) to {out_dir}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nWrote {len(outputs)} file(s) to {out_dir}"))
        self.stdout.write(
            "\nReminder: TIG_Criteria.md, Watch_Criteria.md and TIX_Criteria.md are hand-maintained. "
            "Check the workbook's criteria sheets against them (manage.py compare_excel_criteria shows what changed)."
        )
