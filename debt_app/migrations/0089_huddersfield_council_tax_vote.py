"""
Huddersfield council tax: Do Not Vote.

The workbook's Councils tab has a row "Huddersfield (council tax)" with a
blank status and the note "do not vote 1/12/22". The council import skips it
(blank status), so a case naming Huddersfield council found no rule. The
sheet owner confirmed DO NOT VOTE on 2026-10-13.

Recorded as its own council row. Kirklees Borough Council (which bills
Huddersfield council tax) keeps its own ACCEPT row: the owner was not asked
about Kirklees, so it is not changed here.

Does nothing if a Huddersfield council row already exists.
"""

from django.db import migrations

NAME = "Huddersfield Council"


def forwards(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    if CouncilRule.objects.filter(council_name__iexact=NAME).exists():
        return
    CouncilRule.objects.create(
        council_name=NAME,
        status="DO_NOT_VOTE",
        blocked_reason=(
            "Workbook row 'Huddersfield (council tax)': do not vote 1/12/22. DO NOT VOTE confirmed by the sheet "
            "owner on 2026-10-13. Kirklees Borough Council has its own row."
        ),
    )


def backwards(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    CouncilRule.objects.filter(council_name=NAME, status="DO_NOT_VOTE").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0088_hillingdon_housing_benefit_vote"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
