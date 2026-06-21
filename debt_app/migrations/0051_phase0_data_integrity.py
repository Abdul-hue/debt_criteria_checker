"""
Phase 0 — Data integrity.

1. Delete the junk CreditorCriteria row seeded from a sheet note:
   creditor_name = "ALWAYS USE THE CURRENT BALANCE NOT TOTAL PAYABLE".
   This is not a creditor — it leaked in from a free-text cell.

2. Deduplicate "George Banco": two active rows exist —
     - "GEORGE BANCO"  (representative=EVERYDAY_LOANS)  <- keep (correct rep mapping)
     - "George Banco"  (representative=NONE)            <- deactivate (stale duplicate)
   Both being active makes get_creditor_by_trading_name's iexact .get() raise
   MultipleObjectsReturned. Keep the EVERYDAY_LOANS row; deactivate the NONE one.
"""

from django.db import migrations


JUNK_NAME = "ALWAYS USE THE CURRENT BALANCE NOT TOTAL PAYABLE"


def forward(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    deleted, _ = CreditorCriteria.objects.filter(creditor_name=JUNK_NAME).delete()
    print(f"\n  Deleted {deleted} junk creditor row(s).")

    dup = CreditorCriteria.objects.filter(
        creditor_name__iexact="George Banco", representative="NONE"
    ).update(is_active=False)
    print(f"  Deactivated {dup} duplicate George Banco (NONE) row(s).")


def reverse(apps, schema_editor):
    # Re-activate the George Banco duplicate. The junk row is intentionally not
    # recreated (it was never valid data).
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(
        creditor_name__iexact="George Banco", representative="NONE"
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0050_disable_category3_rules"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
