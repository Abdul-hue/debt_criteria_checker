"""
Remove the BANK-STATEMENTS GlobalCriteria row (2026-11-05).

The rule asked for 12 months of statements for every active or defaulted bank
account on the credit report, and flagged almost every case: advisors collect
statements dated within the last 3 months (TIG-11, the TIG criteria sheet's
"1 full month for every account"), and 12 months of statement payments is a
mortgage / vehicle-finance question only. The rule is gone from the engine,
so its admin row would switch nothing.

Reverse puts the row back as 0090 created it, switched off.
"""

from django.db import migrations


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BANK-STATEMENTS").delete()


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.get_or_create(
        rule_key="BANK-STATEMENTS",
        defaults={
            "criteria_set": "TIG",
            "rule_name": "12 months of bank statements for each bank account",
            "severity": "flag",
            "is_active": False,
            "category": "bank_statements",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0098_seed_pra_group_dca"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
