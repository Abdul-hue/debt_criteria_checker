"""
POD-OVER-500 no longer asks for proof of debt on a debt the credit report
carries (business, 2026-11-17). The rule's logic is in `engine/criteria.py ::
_pod_over_500`; this updates only the admin row's description to match.
"""

from django.db import migrations

OLD = (
    "Debts over £500 require proof of debt. The case can proceed to drafting without individual PODs "
    "if the overall debt level is evidenced."
)
NEW = (
    "Debts over £500 that are not on the credit report require proof of debt. A debt the credit report "
    "carries needs none. The case can proceed to drafting without individual PODs if the overall debt "
    "level is evidenced."
)


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="POD-OVER-500").update(description=NEW)


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="POD-OVER-500").update(description=OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0099_remove_bank_statements_rule"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
