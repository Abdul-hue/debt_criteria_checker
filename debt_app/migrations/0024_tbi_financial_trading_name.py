from django.db import migrations


def add_tbi_trading_name(apps, schema_editor):
    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    tbi = CreditorCriteria.objects.filter(creditor_name='TBI Financial Services').first()
    if tbi is None:
        return
    names = list(tbi.trading_names or [])
    if 'TBI Financial' not in names:
        names.append('TBI Financial')
        tbi.trading_names = names
        tbi.save()


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0023_huntingdonshire_reject_if_employed'),
    ]

    operations = [
        migrations.RunPython(add_tbi_trading_name, migrations.RunPython.noop),
    ]
