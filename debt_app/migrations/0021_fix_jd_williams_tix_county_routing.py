from django.db import migrations


def apply_fixes(apps, schema_editor):
    """
    m3: Set JD Williams representative to TIX.
    m4: Insert 2 missing CountyCouncilRouting entries (Cambridgeshire, East Sussex).

    Source: EXCEL_CRITERIA_REFERENCE.md — Which Representative (TIX) and County Councils sheet.
    """
    CreditorCriteria = apps.get_model('debt_app', 'CreditorCriteria')
    CountyCouncilRouting = apps.get_model('debt_app', 'CountyCouncilRouting')

    # --- m3: JD Williams → TIX ---
    # EXCEL_CRITERIA_REFERENCE.md — Which Representative: TIX
    CreditorCriteria.objects.update_or_create(
        creditor_name='JD Williams',
        defaults={
            'representative': 'TIX',
            'is_active': True,
            'trading_names': [
                'J D Williams', 'JD Williams & Company', 'Simply Be',
                'Jacamo', 'Fashion World', 'Marisota',
            ],
            'parent_group': 'Shop Direct Group',
        },
    )

    # --- m4: Missing county council routing rows ---
    # EXCEL_CRITERIA_REFERENCE.md — County Councils sheet

    cambridgeshire_districts = [
        'Cambridge CC',
        'East Cambridgeshire DC',
        'Fenland DC',
        'Huntingdonshire DC',
        'South Cambridgeshire DC',
    ]
    for district in cambridgeshire_districts:
        CountyCouncilRouting.objects.get_or_create(
            county_name='Cambridgeshire',
            district_name=district,
            defaults={'council_rule': None},
        )

    east_sussex_districts = [
        'Eastbourne BC',
        'Hastings BC',
        'Lewes DC',
        'Rother DC',
        'Wealden DC',
    ]
    for district in east_sussex_districts:
        CountyCouncilRouting.objects.get_or_create(
            county_name='East Sussex',
            district_name=district,
            defaults={'council_rule': None},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0020_fix_barclaycard_rep_slough_status'),
    ]

    operations = [
        migrations.RunPython(apply_fixes, migrations.RunPython.noop),
    ]
