from django.db import migrations

def add_trading_names(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")

    additions = [
        ("Asset Link",                 "Asset Link Capital"),
        ("Funding Corporation",        "Funding Corp"),
        ("Hull and East Yorkshire CU", "Hull & East Yorkshire Credit Union"),
    ]

    for creditor_name, alias in additions:
        obj = CreditorCriteria.objects.get(creditor_name=creditor_name)
        names = obj.trading_names or []
        if alias not in names:
            names.append(alias)
            obj.trading_names = names
            obj.save()

class Migration(migrations.Migration):
    dependencies = [
        ("debt_app", "0028_shell_energy_evolve_rep"),
    ]
    operations = [
        migrations.RunPython(add_trading_names, migrations.RunPython.noop),
    ]
