"""
Deactivate legacy long-name entries for Lowell and Lantern that duplicate
the canonical short-name entries added in migration 0025.

Migration 0008 created:
  - "Lowell Financial"                          (TIX)
  - "Lantern Debt Recovery Limited - IVA or BKY" (WATCH)
  - "Lantern Debt Recovery Limited - TD or DAS or SEQ" (WATCH)

Migration 0025 added canonical short-name entries:
  - "Lowell"  (TIX, trading_names includes "Lowell Financial")
  - "Lantern" (WATCH, trading_names includes the full names above)

The alias map now routes all Lowell/Lantern inputs to the short-name entries.
The long-name entries are redundant and cause the display name to flip
depending on which Aryza name the creditor uses.
"""

from django.db import migrations


LEGACY_NAMES = [
    "Lowell Financial",
    "Lantern Debt Recovery Limited - IVA or BKY",
    "Lantern Debt Recovery Limited - TD or DAS or SEQ",
]


def deactivate_legacy(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(creditor_name__in=LEGACY_NAMES).update(is_active=False)


def reactivate_legacy(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(creditor_name__in=LEGACY_NAMES).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0043_credit_report"),
    ]

    operations = [
        migrations.RunPython(deactivate_legacy, reactivate_legacy),
    ]
