"""
Add the GlobalCriteria row for COUNCIL-DIV-REQUIRED-DI, SWITCHED OFF.

Required DI = ((Debt Level x DIV) + fee) / term. The fee (£4,250) lives in this
row's threshold_value so it can change without a release
(`engine/criteria.py :: _council_div_fee`). Switched on through an approved
Criteria Change, like the missing-evidence rules in 0094.

get_or_create on the key only — deliberately NOT a seed_rule_meta re-run,
which would reset is_active on every other rule.
"""

from decimal import Decimal

from django.db import migrations

RULE = {
    "rule_key": "COUNCIL-DIV-REQUIRED-DI",
    "rule_name": "Council majority: case DI must meet the council's DIV requirement",
    "severity": "hard_block",
    "category": "creditor_specific",
    "threshold_value": Decimal("4250.00"),
    "description": (
        "Where council debt is the majority and a DIV is known, the case DI must be at least "
        "((Debt Level x DIV) + £4,250) / IVA term (72 months with a mortgage, else 60). "
        "If it is lower the case is returned, showing Required DI, Actual DI and Shortfall."
    ),
    "action": "Increase the case DI to the required amount, or return the case.",
}


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    defaults = {k: v for k, v in RULE.items() if k != "rule_key"}
    GlobalCriteria.objects.get_or_create(
        rule_key=RULE["rule_key"],
        defaults={**defaults, "criteria_set": "TIG", "is_active": False},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0094_missing_evidence_rules"),
    ]

    # Reverse is a no-op for the same reason as 0094.
    operations = [
        migrations.RunPython(forward, reverse_code=migrations.RunPython.noop),
    ]
