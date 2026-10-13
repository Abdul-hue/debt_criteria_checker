"""
Hillingdon Council: housing benefit debts are Do Not Vote.

The workbook's Councils tab has a row named just "hilli" (DO NOT VOTE,
05/05/2023, council tax department number). The sheet owner
confirmed on 2026-10-13 that it is Hillingdon Council housing benefit
(London Borough), and that each Hillingdon department votes differently.
The council import skips the "hilli" row, so the stance is recorded as a
per-debt-type vote on the existing Hillingdon row, which keeps WILL_CONSIDER
for everything else.

Does nothing if the Hillingdon row is missing (e.g. a fresh test database)
and never overwrites an existing housing-benefit vote.
"""

from django.db import migrations

HILLINGDON = "Hillingdon Council (London Borough)"


def forwards(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    DebtTypeCouncilVote = apps.get_model("debt_app", "DebtTypeCouncilVote")
    council = CouncilRule.objects.filter(council_name=HILLINGDON).first()
    if council is None:
        return
    DebtTypeCouncilVote.objects.get_or_create(
        council=council, debt_type="HOUSING_BENEFIT", defaults={"status": "DO_NOT_VOTE"},
    )


def backwards(apps, schema_editor):
    DebtTypeCouncilVote = apps.get_model("debt_app", "DebtTypeCouncilVote")
    DebtTypeCouncilVote.objects.filter(
        council__council_name=HILLINGDON, debt_type="HOUSING_BENEFIT", status="DO_NOT_VOTE",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0087_creditor_status_unknown_choice"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
