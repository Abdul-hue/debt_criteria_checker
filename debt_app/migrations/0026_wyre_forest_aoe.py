"""
Seed CouncilRule for Wyre Forest District Council with reject_if_aoe_in_place=True.

Wyre Forest will not participate in an IVA where an Attachment of Earnings Order
is already in force — it expects to collect via AoE and will reject the proposal.
"""
from django.db import migrations


def seed_wyre_forest_aoe(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    CouncilRule.objects.update_or_create(
        council_name="Wyre Forest District Council",
        defaults={"reject_if_aoe_in_place": True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0025_seed_debt_purchasers"),
    ]

    operations = [
        migrations.RunPython(seed_wyre_forest_aoe, migrations.RunPython.noop),
    ]
