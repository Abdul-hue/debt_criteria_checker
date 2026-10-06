from django.db import migrations

# The Lead Generation department (seeded by `seed_departments`) gets the new
# lead_gen_check feature. Reporting and criteria-change features are NOT
# enabled for anyone here — an admin opts departments in explicitly.


def enable(apps, schema_editor):
    Department = apps.get_model("debt_app", "Department")
    DepartmentFeatureAccess = apps.get_model("debt_app", "DepartmentFeatureAccess")
    for dept in Department.objects.filter(slug="lead-generation"):
        DepartmentFeatureAccess.objects.update_or_create(
            department=dept, feature_key="lead_gen_check", defaults={"is_enabled": True},
        )


def disable(apps, schema_editor):
    DepartmentFeatureAccess = apps.get_model("debt_app", "DepartmentFeatureAccess")
    DepartmentFeatureAccess.objects.filter(
        department__slug="lead-generation", feature_key="lead_gen_check",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0078_lead_gen_and_criteria_change_control"),
    ]

    operations = [
        migrations.RunPython(enable, reverse_code=disable),
    ]
