"""
Add the BPO-DEBT GlobalCriteria row so the new rule shows in the admin rules
list and can be switched on/off there.

get_or_create on this one key only — deliberately NOT a seed_rule_meta re-run,
which would reset is_active on every other rule. Mirrors the seed_rule_meta.py
source-of-truth entry.
"""

from django.db import migrations


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.get_or_create(
        rule_key="BPO-DEBT",
        defaults={
            "criteria_set": "TIG",
            "rule_name": "BPO debt - actual creditor needed",
            "severity": "flag",
            "is_active": True,
            "category": "creditor_specific",
            "description": (
                "A debt is listed under a BPO name. BPO is an agency holding the "
                "debt, not the actual creditor."
            ),
            "action": "Confirm who the actual creditor is for each BPO debt.",
        },
    )


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BPO-DEBT").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0082_lead_gen_dmp_review_required"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
