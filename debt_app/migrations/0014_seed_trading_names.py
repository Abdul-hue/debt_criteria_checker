"""Merge Phase 2 creditor trading-name variants (idempotent)."""

from django.db import migrations

PHASE2_TRADING_NAMES = {
    "Commsave Credit Union": [
        "Commsave",
        "Commsave CU",
        "Commsave Credit Union Limited",
        "Commsave Credit Union Ltd",
    ],
    "CAMBRIAN Credit Union": [
        "Cambrian",
        "Cambrian CU",
        "Cambrian Credit Union",
        "Cambrian Credit Union Limited",
    ],
    "Bamboo": [
        "Bamboo Loans",
        "Bamboo Loans Limited",
        "Bamboo Limited",
    ],
    "Moneybarn": [
        "Moneybarn Limited",
        "Moneybarn No. 1 Limited",
        "Moneybarn Finance",
    ],
    "Volkswagen Financial Services": [
        "VWFS",
        "Volkswagen Finance",
        "VW Finance",
        "Volkswagen Financial Services UK Limited",
    ],
    "TBI Financial Services": [
        "TBI",
        "TBI Financial Services Limited",
    ],
    "Buddy Loans": [
        "Buddy",
        "Advancis Ltd",
        "Advancis Limited",
    ],
    "Salary Finance": [
        "Salary Finance Limited",
    ],
    "Plata Loans": [
        "Plata",
    ],
    "Amigo Loans": [
        "Amigo",
        "Amigo Loans",
        "Amigo Loans Limited",
    ],
    "Penny Post Credit Union": [
        "Penny Post",
        "Penny Post CU",
    ],
    "No1 Copperpot Credit Union": [
        "Copperpot",
        "No1 Copperpot",
        "No 1 Copperpot Credit Union",
    ],
}


def _merge_trading_names(existing, additions):
    merged = list(existing or [])
    for name in additions:
        if name not in merged:
            merged.append(name)
    return merged


def seed_trading_names(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for canonical, names in PHASE2_TRADING_NAMES.items():
        row = CreditorCriteria.objects.filter(creditor_name__iexact=canonical).first()
        if not row:
            continue
        row.trading_names = _merge_trading_names(row.trading_names, names)
        row.save(update_fields=["trading_names"])


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0013_seed_legacy_creditors"),
    ]

    operations = [
        migrations.RunPython(seed_trading_names, migrations.RunPython.noop),
    ]
