from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0068_alter_creditornonacceptmilestone_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditormocalert',
            name='emailed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditornonacceptmilestone',
            name='emailed',
            field=models.BooleanField(default=False),
        ),
    ]
