from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0014_seed_trading_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='councilrule',
            name='reject_if_sole',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='councilrule',
            name='include_current_year_ct',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='councilrule',
            name='reject_if_joint_one_employed',
            field=models.BooleanField(default=False),
        ),
    ]
