"""
Fix two seed data errors identified against EXCEL_CRITERIA_REFERENCE.md.

- Barclaycard belongs to EVOLVE (Which Representative sheet), not WATCH.
- Slough Borough Council is REJECT (Councils sheet), not DO_NOT_VOTE.

This migration corrects existing database rows so that a full reseed is not
required on already-deployed databases.
"""

# EXCEL_CRITERIA_REFERENCE.md — Which Representative / Councils sheet

from django.db import migrations


def fix_barclaycard_and_slough(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CouncilRule = apps.get_model("debt_app", "CouncilRule")

    # Barclaycard is listed under EVOLVE in the Which Representative sheet.
    CreditorCriteria.objects.filter(creditor_name="Barclaycard").update(
        representative="EVOLVE"
    )

    # Slough Borough Council is REJECT in the Councils sheet.
    CouncilRule.objects.filter(council_name="Slough Borough Council").update(
        status="REJECT"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0019_module6_copperpot_trading_name"),
    ]

    operations = [
        migrations.RunPython(fix_barclaycard_and_slough, migrations.RunPython.noop),
    ]
