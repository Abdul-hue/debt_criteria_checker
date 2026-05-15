from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0004_rename_name_to_creditor_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditorcriteria',
            name='dividend_notes',
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Free-text notes for caseworkers about this creditor's dividend requirements",
            ),
        ),
    ]
