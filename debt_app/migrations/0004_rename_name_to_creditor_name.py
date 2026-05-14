from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0003_remove_watch_tix_evolve_booleans_add_account_age'),
    ]

    operations = [
        migrations.RenameField(
            model_name='creditorcriteria',
            old_name='name',
            new_name='creditor_name',
        ),
    ]
