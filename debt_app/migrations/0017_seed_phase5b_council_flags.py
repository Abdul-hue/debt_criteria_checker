from django.db import migrations


def seed_phase5b_council_flags(apps, schema_editor):
    CouncilRule = apps.get_model('debt_app', 'CouncilRule')

    for council_name in (
        'Cardiff Council',
        'Walsall Council',
        'Waltham Forest Council',
    ):
        CouncilRule.objects.update_or_create(
            council_name=council_name,
            defaults={'include_current_year_ct': True},
        )

    CouncilRule.objects.update_or_create(
        council_name='Huntingdonshire District Council',
        defaults={
            'reject_if_benefits_only': True,
            'reject_if_any_benefits': True,
            'reject_if_joint_one_employed': True,
            'reject_if_previous_iva': True,
            'reject_if_dro_criteria_met': True,
            'reject_if_aoe_in_place': True,
            'reject_if_joint_one_party_only': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0016_seed_shropshire_reject_if_sole'),
    ]

    operations = [
        migrations.RunPython(seed_phase5b_council_flags, migrations.RunPython.noop),
    ]
