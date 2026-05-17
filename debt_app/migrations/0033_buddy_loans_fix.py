from django.db import migrations


def fix_buddy_loans(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(creditor_name="Buddy Loans").update(
        status="DO_NOT_VOTE",
        min_dividend_pence=50,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0032_seed_remaining_unknowns"),
    ]

    operations = [
        migrations.RunPython(
            fix_buddy_loans,
            migrations.RunPython.noop,
        ),
    ]
