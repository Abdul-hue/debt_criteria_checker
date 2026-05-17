from django.db import migrations


def set_huntingdonshire_reject_if_employed(apps, schema_editor):
    CouncilRule = apps.get_model('debt_app', 'CouncilRule')
    # Huntingdonshire DC prefers AOE over IVA for employed clients — reject sole employed cases.
    CouncilRule.objects.filter(
        council_name='Huntingdonshire District Council',
    ).update(reject_if_employed=True)


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0022_fix_seed_errors'),
    ]

    operations = [
        migrations.RunPython(set_huntingdonshire_reject_if_employed, migrations.RunPython.noop),
    ]
