"""
Add "No1 Copperpot CU" as a trading name for No1 Copperpot Credit Union.

The test payload uses the short form "No1 Copperpot CU" which was not in the
original trading_names list seeded by 0014_seed_trading_names. The engine uses
get_creditor_by_trading_name() which requires an exact (case-insensitive) match
against creditor_name or any entry in trading_names.

Source: GENERAL CREDITOR sheet — reject_if_police_employed flag (Module 6).
"""

from django.db import migrations


def _add_copperpot_trading_name(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    try:
        copperpot = CreditorCriteria.objects.get(creditor_name="No1 Copperpot Credit Union")
        names = list(copperpot.trading_names or [])
        if "No1 Copperpot CU" not in names:
            names.append("No1 Copperpot CU")
            copperpot.trading_names = names
            copperpot.save(update_fields=["trading_names"])
    except CreditorCriteria.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0018_add_everyday_loans_representative"),
    ]

    operations = [
        migrations.RunPython(_add_copperpot_trading_name, migrations.RunPython.noop),
    ]
