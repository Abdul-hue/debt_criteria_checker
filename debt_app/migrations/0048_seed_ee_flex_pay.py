from django.db import migrations


def seed_ee_flex_pay(apps, schema_editor):
    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    CreditorCriteria.objects.update_or_create(
        creditor_name='EE FLEX PAY',
        defaults={
            'representative': 'NONE',
            'status': 'ACCEPT',
            'is_active': True,
            'source_sheet': 'GENERAL CREDITOR',
        },
    )


def reverse_seed(apps, schema_editor):
    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    CreditorCriteria.objects.filter(creditor_name='EE FLEX PAY').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0047_add_department_feature_permissions'),
    ]

    operations = [
        migrations.RunPython(seed_ee_flex_pay, reverse_seed),
    ]
