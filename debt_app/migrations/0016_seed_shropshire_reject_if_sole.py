from django.db import migrations


def seed_shropshire_reject_if_sole(apps, schema_editor):
    CouncilRule = apps.get_model('debt_app', 'CouncilRule')
    CouncilRule.objects.update_or_create(
        council_name='Shropshire Council',
        defaults={'reject_if_sole': True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0015_councilrule_reject_if_sole'),
    ]

    operations = [
        migrations.RunPython(seed_shropshire_reject_if_sole, migrations.RunPython.noop),
    ]
