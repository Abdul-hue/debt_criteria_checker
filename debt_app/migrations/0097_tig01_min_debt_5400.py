"""
Lower the TIG-01 minimum unsecured debt from £6,000 to £5,400 (2026-11-02).

The engine reads the figure from `IVA_MIN_DEBT` in engine/criteria.py (the
threshold is code-managed); this keeps the stored row the criteria admin
shows in step. Threshold and description only -- severity, is_active and
every other rule untouched. Mirrors the seed_rule_meta.py entry.
"""

from decimal import Decimal

from django.db import migrations


RULE = {
    "threshold_value": Decimal("5400.00"),
    "description": "Total unsecured debt must be at least £5,400. Below this threshold the case cannot proceed.",
}

PREVIOUS = {
    "threshold_value": Decimal("6000.00"),
    "description": "Total unsecured debt must be at least £6,000. Below this threshold the case cannot proceed.",
}


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="TIG-01").update(**RULE)


def reverse(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    GlobalCriteria.objects.filter(rule_key="TIG-01").update(**PREVIOUS)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0096_bpo_debt_dca_wording"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
