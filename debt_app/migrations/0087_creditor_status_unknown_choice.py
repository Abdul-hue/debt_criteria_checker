"""
Add UNKNOWN to CreditorCriteria.status choices.

The engine has always understood a stored status of UNKNOWN ("has no
recorded standing position on IVA proposals"; never counted as an
acceptance), but the choice was missing from the model, so the criteria
change workflow and the edit screens could not set it. It is the safe value
for a creditor whose stance the sheet owner has not confirmed — for example
the creditors that lost the retired Evolve representative, and Zilch.

Choices only: no column change, no row is modified.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0086_creditor_young_account_dividend"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditorcriteria",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACCEPT", "Accept"),
                    ("REJECT", "Reject"),
                    ("WILL_CONSIDER", "Will Consider"),
                    ("DO_NOT_VOTE", "Do Not Vote"),
                    ("CONDITIONAL_VOTER", "Conditional Voter"),
                    ("UNKNOWN", "Unknown - stance not yet confirmed"),
                ],
                default="ACCEPT",
                max_length=20,
            ),
        ),
    ]
