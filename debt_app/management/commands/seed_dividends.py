"""
Seed CreditorCriteria with dividend requirements.

Source of truth: TIP CRITERIA & VOTING HISTORY.xlsx — "Dividends " sheet.
Run with: python manage.py seed_dividends [--dry-run]
"""

import re
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria

# Data from Dividends_Criteria.md / Excel "Dividends " sheet
DIVIDEND_DATA = [
    ("Amigo", None, "DO NOT REQUIRE A DIV NOW"),
    ("Asset Link", 50, ""),
    ("Believe Housing", 40, ""),
    ("Beyond Housing", 30, ""),
    ("Buckinghamshire Council", 50, "If joint CTAX debt then they don’t vote and you don’t need to worry about the DIV"),
    ("Cardiff Credit Union", 45, ""),
    ("Chorley Council", 30, ""),
    ("Clockwise Credit Union", 50, "Needs to be 2 months old"),
    ("Colchester Council", 45, ""),
    ("East Suffolk Council", 50, ""),
    ("FCE Bank", 75, ""),
    ("Funding Circle", 30, "Equity Issues"),
    ("Funding Corp", 50, ""),
    ("Glenside Finance", 25, ""),
    ("Guarantor My Loan", 50, ""),
    ("Hull and East Yorkshire CU", 60, ""),
    ("Medway Council", 25, "needs to be higher than 25p"),
    ("Ratesetter", 25, "if under 6 months old it 50p"),
    ("Reading Council", 60, ""),
    ("Shell Energy", None, "evolve criteria"),
    ("South East Water", 40, "Get div as high as possible"),
    ("Specialist Motor Finance", 50, ""),
    ("Transave Credit Union", 60, "needs to be at least 3 months old"),
    ("Wandsworth Council", 40, ""),
    ("Worcester Council", 75, ""),
    ("Wyre Forest Council", 50, "if AOE in place then they will REJECT"),
]

class Command(BaseCommand):
    help = "Seed CreditorCriteria with dividend requirements from the Dividends sheet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be seeded without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created_count = 0
        updated_count = 0

        for name, div, notes in DIVIDEND_DATA:
            defaults = {
                "min_dividend_pence": div,
                "dividend_notes": notes,
                "is_active": True,
            }

            if dry_run:
                self.stdout.write(f"  [DRY RUN] {name}: {div}p - {notes}")
                continue

            creditor, created = CreditorCriteria.objects.update_or_create(
                creditor_name=name,
                defaults=defaults,
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"Done. Created: {created_count}  Updated: {updated_count}"
            ))
