"""
Report what changed between two copies of the criteria workbook.

    python manage.py compare_excel_criteria --old old.xlsx --new new.xlsx
    python manage.py compare_excel_criteria --old old.xlsx --new new.xlsx --out docs/criteria-source/diff.txt

Rows are matched by creditor / council name, not by row number, so inserted
rows do not make everything below them look changed. Read-only.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from debt_app.services.excel_criteria import compare_workbooks


class Command(BaseCommand):
    help = "Compare two versions of the criteria workbook by creditor / council name (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--old", required=True, help="Previous workbook")
        parser.add_argument("--new", required=True, help="New workbook")
        parser.add_argument("--out", default=None, help="Also write the report to this file")

    def handle(self, *args, **options):
        old, new = Path(options["old"]), Path(options["new"])
        for p in (old, new):
            if not p.exists():
                raise CommandError(f"Workbook not found: {p}")
        text = compare_workbooks(old, new)
        if options["out"]:
            out = Path(options["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Report written to {out}\n"))
        self.stdout.write(text)
