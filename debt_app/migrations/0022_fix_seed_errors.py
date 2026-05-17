"""
Fix four seed data errors identified against EXCEL_CRITERIA_REFERENCE.md.

  M3: Colchester Council CreditorCriteria min_dividend_pence 65 → 45
  M4: Huntingdonshire CouncilRule reject_if_joint_one_party_only → True
  M6: Wyre Forest CouncilRule reject_if_aoe_in_place → True
  (M5 JD Williams _SHOP_DIRECT_NAMES is code-only — no DB change needed)
"""

from django.db import migrations


def fix_seed_errors(apps, schema_editor):
    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    CouncilRule = apps.get_model('debt_app', 'CouncilRule')

    # M3 — Colchester Council minimum dividend: 65p → 45p
    for name in ('Colchester Council', 'Colchester Borough Council'):
        CreditorCriteria.objects.filter(creditor_name=name).update(min_dividend_pence=45)
    CouncilRule.objects.filter(council_name__icontains='Colchester').update(min_dividend_pence=45)

    # M4 — Huntingdonshire: add missing reject_if_joint_one_party_only flag
    CouncilRule.objects.filter(
        council_name='Huntingdonshire District Council',
    ).update(reject_if_joint_one_party_only=True)

    # M6 — Wyre Forest: promote AOE note to hard reject flag
    CouncilRule.objects.update_or_create(
        council_name='Wyre Forest District Council',
        defaults={'reject_if_aoe_in_place': True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0021_fix_jd_williams_tix_county_routing'),
    ]

    operations = [
        migrations.RunPython(fix_seed_errors, migrations.RunPython.noop),
    ]
