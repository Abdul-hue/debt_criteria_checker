"""
Add EVERYDAY_LOANS as a valid representative choice for CreditorCriteria.

Which Representative sheet (col G, row 1): "EVERYDAY LOANS"
Sub-entries: George Banco (row 3), Trust II / Trust Two (row 4).
Note: "ALWAYS USE THE CURRENT BALANCE NOT TOTAL PAYABLE" (col G, row 2).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0017_seed_phase5b_council_flags"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditorcriteria",
            name="representative",
            field=models.CharField(
                max_length=15,
                choices=[
                    ("WATCH", "Watch"),
                    ("TIX", "TIX"),
                    ("EVOLVE", "Evolve"),
                    ("EVERYDAY_LOANS", "Everyday Loans"),
                    ("NONE", "None"),
                ],
                default="NONE",
            ),
        ),
    ]
