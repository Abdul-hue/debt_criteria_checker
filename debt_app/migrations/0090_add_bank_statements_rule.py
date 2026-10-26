"""
Add the BANK-STATEMENTS GlobalCriteria row so the new rule shows in the admin
rules list and can be switched on/off there.

get_or_create on this one key only — deliberately NOT a seed_rule_meta re-run,
which would reset is_active on every other rule. Mirrors the seed_rule_meta.py
source-of-truth entry.
"""

from django.db import migrations


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.get_or_create(
        rule_key="BANK-STATEMENTS",
        defaults={
            "criteria_set": "TIG",
            "rule_name": "12 months of bank statements for each bank account",
            "severity": "flag",
            "is_active": True,
            "category": "bank_statements",
            "description": (
                "Every active or defaulted bank account on the credit report (current, "
                "savings or basic bank account) needs bank statements covering the 12 "
                "months before the case was added to CAT, or from when the account was "
                "opened if that is later. Flags any account with no matched statements, "
                "gaps in coverage, or statements whose period cannot be read."
            ),
            "action": (
                "Upload the missing statements for each listed account, or record why "
                "the customer cannot provide them."
            ),
        },
    )


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BANK-STATEMENTS").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0089_huddersfield_council_tax_vote"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
