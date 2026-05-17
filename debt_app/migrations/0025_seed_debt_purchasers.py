"""
Seed canonical short-name rows for three debt-purchaser creditors that appear
in real payloads under normalised names but have no CreditorCriteria DB entry.

Without these rows the engine emits CREDITOR-UNKNOWN for every Lowell, Lantern,
and Perch Capital debt, inflating the majority denominator without contributing
any YES votes.

Sources:
  - Lowell: TIX_CREDITORS list (migration 0008) — full name "Lowell Financial"
  - Lantern: WATCH_REPRESENTATIVES list (migration 0008) — "Lantern Debt Recovery Limited"
  - Perch Capital: not in 0008; independent debt purchaser, no specific representative
"""

from django.db import migrations


DEBT_PURCHASERS = [
    {
        "creditor_name": "Lowell",
        "representative": "TIX",
        "status": "ACCEPT",
        "trading_names": [
            "Lowell Financial",
            "Lowell Portfolio I Ltd",
            "Lowell Portfolio I LTD",
            "Lowell Portfolio",
        ],
    },
    {
        "creditor_name": "Lantern",
        "representative": "WATCH",
        "status": "ACCEPT",
        "trading_names": [
            "Lantern Debt Recovery Services Ltd",
            "Lantern Debt Recovery Limited",
            "Lantern Debt Recovery Limited - IVA or BKY",
            "Lantern Debt Recovery Limited - TD or DAS or SEQ",
        ],
    },
    {
        "creditor_name": "Perch Capital",
        "representative": "NONE",
        "status": "ACCEPT",
        "trading_names": [
            "Perch Capital Limited",
            "Perch Capital Ltd",
        ],
    },
]


def seed_debt_purchasers(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for data in DEBT_PURCHASERS:
        obj, created = CreditorCriteria.objects.get_or_create(
            creditor_name=data["creditor_name"],
            defaults={
                "representative": data["representative"],
                "status": data["status"],
                "trading_names": data["trading_names"],
                "is_active": True,
            },
        )
        if not created:
            # Idempotent: update fields if row already exists (e.g. partial prior run)
            obj.representative = data["representative"]
            obj.status = data["status"]
            obj.trading_names = data["trading_names"]
            obj.is_active = True
            obj.save()


def reverse_seed(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for data in DEBT_PURCHASERS:
        CreditorCriteria.objects.filter(creditor_name=data["creditor_name"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0024_tbi_financial_trading_name"),
    ]

    operations = [
        migrations.RunPython(seed_debt_purchasers, reverse_seed),
    ]
