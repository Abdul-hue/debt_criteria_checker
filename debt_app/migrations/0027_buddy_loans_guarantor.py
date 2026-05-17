from django.db import migrations

def set_buddy_loans_guarantor(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(creditor_name="Buddy Loans").update(
        requires_pg_called_up=True
    )

class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0026_wyre_forest_aoe"),
    ]
    operations = [
        migrations.RunPython(set_buddy_loans_guarantor, migrations.RunPython.noop),
    ]
