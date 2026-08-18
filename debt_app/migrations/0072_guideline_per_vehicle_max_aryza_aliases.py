from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0071_application_source_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='expenditureguideline',
            name='per_vehicle_max',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='expenditureguideline',
            name='aryza_aliases',
            field=models.TextField(
                blank=True, default='',
                help_text="Comma-separated Aryza expense category names that map to "
                          "this guideline, e.g. 'Groceries, Food Shopping'.",
            ),
        ),
    ]
