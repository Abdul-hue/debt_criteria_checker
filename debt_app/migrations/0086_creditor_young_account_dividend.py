"""
Age-tiered minimum dividend for a creditor.

Workbook 2026-10-12, Loans by Mal: "if under 6 months but older than 3 months -
has to 40p/£". No existing field could express a dividend that depends on the
account's age, so two nullable fields are added. Schema only: no rows are
changed here; the values for Loans by Mal go through the criteria change
workflow (build_criteria_change_from_excel).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0085_seed_debt_collectors"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditorcriteria",
            name="young_account_months",
            field=models.IntegerField(
                blank=True, null=True,
                help_text="Accounts younger than this many months need young_account_min_dividend_pence instead of min_dividend_pence.",
            ),
        ),
        migrations.AddField(
            model_name="creditorcriteria",
            name="young_account_min_dividend_pence",
            field=models.IntegerField(
                blank=True, null=True,
                help_text="Minimum dividend (pence in the pound) while the account is younger than young_account_months.",
            ),
        ),
    ]
