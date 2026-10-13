"""
Seed the starting DebtCollector list and re-word the BPO-DEBT rule row.

BPO-DEBT was first built to match the literal word "BPO". The manager's brief
(2026-10-12) clarified that "BPO" means debt collectors in general (e.g.
Marston): a debt entered in Aryza under a collector is not the actual debt.
The full list (~100 names) will be loaded with `import_debt_collectors`.

Starting names: Marston (the manager's example) plus the three collectors the
creditor criteria already hold as DO_NOT_VOTE. Debt purchasers (Cabot, Lowell,
Intrum, PRA, ...) are deliberately NOT here — they own the debt.

get_or_create / update on single keys only — no seed_rule_meta re-run.
"""

from django.db import migrations


STARTING_COLLECTORS = ["Marston", "BPO Collections", "CCS Collect", "Moorcroft"]

RULE_TEXT = {
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
    DebtCollector = apps.get_model("debt_app", "DebtCollector")
    for name in STARTING_COLLECTORS:
        DebtCollector.objects.get_or_create(name=name)
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="BPO-DEBT").update(**RULE_TEXT)


def reverse(apps, schema_editor):
    DebtCollector = apps.get_model("debt_app", "DebtCollector")
    DebtCollector.objects.filter(name__in=STARTING_COLLECTORS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0084_debt_collector"),
        ("debt_app", "0083_add_bpo_debt_rule"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
