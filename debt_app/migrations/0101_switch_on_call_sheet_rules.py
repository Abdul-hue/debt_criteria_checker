"""
Switch ON the creditor call-sheet rules (manager, 2026-11-20): HMRC-CALL-SHEET,
ARREARS-CREDITOR-CALL and COUNCIL-TAX-EVIDENCE.

Migration 0094 seeded them OFF until CAT sent their fields
(`creditor_call_completed`, `in_arrears`, `div_returned`, `has_pod`); CAT sends
all of them now. This is the approved Criteria Change that 0094 waits for.

SELF-EMPLOYED-CALL-SHEET stays OFF: the business has not yet decided where the
HMRC call for a self-employed client with no HMRC debt is recorded.

Also brings COUNCIL-TAX-EVIDENCE's description into line with the rule: every
voting council -- Will Consider and Conditional Voter too -- needs a call sheet.
"""

from django.db import migrations

SWITCHED_ON = ("HMRC-CALL-SHEET", "ARREARS-CREDITOR-CALL", "COUNCIL-TAX-EVIDENCE")

OLD_COUNCIL = (
    "Non-voting councils require proof of debt. Accepting, rejecting and DIV councils "
    "require a call sheet before SIP."
)
NEW_COUNCIL = (
    "Non-voting councils require proof of debt. Every voting council (accepting, rejecting, "
    "DIV, Will Consider and Conditional Voter) requires a call sheet before SIP."
)


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key__in=SWITCHED_ON).update(is_active=True)
    GlobalCriteria.objects.filter(rule_key="COUNCIL-TAX-EVIDENCE").update(description=NEW_COUNCIL)


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key__in=SWITCHED_ON).update(is_active=False)
    GlobalCriteria.objects.filter(rule_key="COUNCIL-TAX-EVIDENCE").update(description=OLD_COUNCIL)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0100_pod_over_500_credit_report"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
