"""
Audit CreditorCriteria free-text notes for structured fields that may
be missing (gap) despite the notes implying they should be set.

Usage:
    python manage.py audit_criteria_notes
    python manage.py audit_criteria_notes --csv
    python manage.py audit_criteria_notes --fix-safe
"""

import csv
import re
from django.conf import settings
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria

PATTERNS = [
    (
        r"(\d+)\s*p\s*/?\s*£|(\d+)\s*p\s*/?\s*pound",
        "min_dividend_pence",
    ),
    (
        r"months?\s+old|account\s+age|less\s+than\s+\d+\s+months?",
        "account_age_months",
    ),
    (
        r"\bCCJ\b",
        "reject_if_ccj",
    ),
    (
        r"\bAOE\b|attachment\s+of\s+earnings",
        "reject_if_aoe",
    ),
    (
        r"I&E|income.{0,15}expenditure.{0,25}match|match.{0,25}application",
        "reject_if_ie_doesnt_match_application",
    ),
    (
        r"recent\s+spend|spend\s+in\s+last\s+\d+\s+months?",
        "reject_if_recent_spend_months",
    ),
    (
        r"repossess|vehicle\s+arrears",
        "vehicle_arrears_repossession_months",
    ),
    (
        r"arrangement.{0,25}call|call.{0,25}arrangement",
        "requires_arrangement_call_before_proposing",
    ),
]

NONE_FIELDS = {
    "min_dividend_pence",
    "account_age_months",
    "reject_if_recent_spend_months",
    "vehicle_arrears_repossession_months",
}

BOOL_FIELDS = {
    "reject_if_ccj",
    "reject_if_aoe",
    "reject_if_ie_doesnt_match_application",
    "requires_arrangement_call_before_proposing",
}


def _is_gap(field_name, current_value):
    if field_name in NONE_FIELDS:
        return current_value is None
    return current_value is False


class Command(BaseCommand):
    help = "Audit free-text criteria/dividend notes against structured fields"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Write results to audit_criteria_notes.csv in the project root",
        )
        parser.add_argument(
            "--fix-safe",
            action="store_true",
            help="Auto-set min_dividend_pence where None and a value can be extracted",
        )

    def handle(self, *args, **options):
        do_csv = options["csv"]
        do_fix = options["fix_safe"]

        creditors = CreditorCriteria.objects.filter(is_active=True).exclude(
            criteria_notes="",
            dividend_notes="",
        )
        # Also include rows where either field is non-null/non-empty
        from django.db.models import Q
        creditors = CreditorCriteria.objects.filter(is_active=True).filter(
            Q(criteria_notes__isnull=False) | Q(dividend_notes__isnull=False)
        ).exclude(
            Q(criteria_notes="") & Q(dividend_notes="")
        )

        rows = []
        gap_count = 0
        creditor_names_with_gaps = set()

        for c in creditors:
            notes_text = (c.criteria_notes or "") + " " + (c.dividend_notes or "")
            notes_text = notes_text.strip()
            if not notes_text:
                continue

            for pattern, field_name in PATTERNS:
                m = re.search(pattern, notes_text, re.IGNORECASE)
                if not m:
                    continue

                current_value = getattr(c, field_name)
                gap = _is_gap(field_name, current_value)
                status = "GAP" if gap else "OK"

                if gap:
                    gap_count += 1
                    creditor_names_with_gaps.add(c.creditor_name)

                rows.append({
                    "creditor_name": c.creditor_name,
                    "pattern_matched": pattern,
                    "field_needed": field_name,
                    "current_value": str(current_value),
                    "status": status,
                    "_match": m,
                    "_obj": c,
                })

        # --fix-safe: only min_dividend_pence, only None, never overwrite
        if do_fix:
            for row in rows:
                if row["field_needed"] != "min_dividend_pence":
                    continue
                if row["status"] != "GAP":
                    continue
                m = row["_match"]
                try:
                    extracted = int(m.group(1) or m.group(2))
                except (IndexError, TypeError, ValueError):
                    continue
                obj = row["_obj"]
                if obj.min_dividend_pence is None:
                    obj.min_dividend_pence = extracted
                    obj.save(update_fields=["min_dividend_pence"])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"AUTO-SET min_dividend_pence={extracted} for {obj.creditor_name}"
                        )
                    )
                else:
                    self.stdout.write(
                        f"SKIP {obj.creditor_name}: min_dividend_pence already set to {obj.min_dividend_pence}"
                    )

        # Console output
        for row in rows:
            line = (
                f"{row['creditor_name']} | {row['pattern_matched']} | "
                f"{row['field_needed']} | {row['current_value']} | {row['status']}"
            )
            if row["status"] == "GAP":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(self.style.SUCCESS(line))

        summary = f"{gap_count} gap(s) found across {len(creditor_names_with_gaps)} creditor(s)"
        self.stdout.write(self.style.SUCCESS(summary))

        # --csv output
        if do_csv:
            csv_path = settings.BASE_DIR / "audit_criteria_notes.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["creditor_name", "pattern_matched", "field_needed", "current_value", "status"]
                )
                for row in rows:
                    writer.writerow([
                        row["creditor_name"],
                        row["pattern_matched"],
                        row["field_needed"],
                        row["current_value"],
                        row["status"],
                    ])
            self.stdout.write(self.style.SUCCESS("Written to audit_criteria_notes.csv"))
