from django.db import migrations

def set_shell_energy_evolve(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    CreditorCriteria.objects.filter(creditor_name="Shell Energy").update(
        representative="EVOLVE"
    )

class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0027_buddy_loans_guarantor"),
    ]
    operations = [
        migrations.RunPython(set_shell_energy_evolve, migrations.RunPython.noop),
    ]
