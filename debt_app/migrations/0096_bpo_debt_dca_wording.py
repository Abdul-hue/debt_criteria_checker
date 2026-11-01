"""
Re-word the BPO-DEBT rule row as "Debt Collection Agency (DCA)" (2026-10-30).

BPO-DEBT stays the rule key. The old action told the caseworker to upload
proof of debt "not from the collector", which read as rejecting the DCA's
proof of debt; it is kept on the case at this stage, and POD from the actual
creditor is needed as well. Text only -- severity, is_active and every other
rule untouched. Mirrors the seed_rule_meta.py entry.
"""

from django.db import migrations


RULE_TEXT = {
    "rule_name": "Debt Collection Agency (DCA) listed instead of the actual creditor",
    "description": (
        "A debt is listed in Aryza under a Debt Collection Agency (DCA) — a debt collector, "
        "bailiff or enforcement agency — not the company the debt is owed to. The agencies "
        "are kept in the Debt Collectors list."
    ),
    "action": (
        "Identify the actual creditor and correct the creditor name in Aryza. Do not reject "
        "the proof of debt from the DCA at this stage; proof of debt from the actual creditor "
        "will also be needed."
    ),
}

PREVIOUS_TEXT = {
    "rule_name": "Debt collector listed instead of debt provider",
    "description": (
        "A debt is listed in Aryza under a debt collector (BPO), not the company "
        "the debt is owed to. The collectors are kept in the Debt Collectors list."
    ),
    "action": (
        "Change the creditor name in Aryza to the actual debt provider and upload "
        "proof of debt from that provider, not from the collector."
    ),
}


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BPO-DEBT").update(**RULE_TEXT)


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BPO-DEBT").update(**PREVIOUS_TEXT)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0095_council_div_required_di"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
