from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0002_extend_criteria_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='creditorcriteria',
            name='is_watch',
        ),
        migrations.RemoveField(
            model_name='creditorcriteria',
            name='is_tix',
        ),
        migrations.RemoveField(
            model_name='creditorcriteria',
            name='is_evolve',
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='account_age_months',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text='Age of the account in months. Used for Shop Direct account age rules.',
            ),
        ),
    ]
