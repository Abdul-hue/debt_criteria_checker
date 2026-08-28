"""
Fix the SFS guideline sync from 0073_sync_sfs_guidelines_from_case_assessment
against the ACTUAL live case-assessment-tool production data (pulled via its
GET /api/assessments/guideline-categories/ endpoint, 2026-08-18), which
0073's Supabase pull had gotten wrong in several ways:

  1. Category names: 0073 renamed 'Home and Contents' / 'Communications and
     Leisure' (plural) down to 'Home and Content' / 'Communication and
     Leisure' (singular), believing the singular forms were canonical.
     They are not — case-assessment-backend's own migration 0033 renamed
     singular -> plural years ago and nothing renamed it back; production's
     live API confirms the plural names. Renaming back here.

  2. Household-composition child columns (adult_1_child_1..5,
     adult_2_child_1..5) were left at 0.00 for every guideline that grades
     by household size, when production has real, non-zero, graduated
     values in every one of them. debt_app.sfs_calculator.get_guideline_rate
     reads these columns directly via getattr() — it does NOT evaluate the
     'formula' text — so for any household with children these guidelines
     were silently resolving to a 0.00 floor/ceiling. Affected: hobbies,
     mot_spares, food_milk_groceries, laundry_dry_cleaning,
     clothing_footwear, toiletries, health_minimum.

  3. min/max constraint flags and/or base rates wrong on: home_phone_internet
     and mobile_phones (min/max swapped), hairdressing (min/max both wrong
     AND a base rate production doesn't have), hobbies/food_milk_groceries/
     laundry_dry_cleaning/clothing_footwear/toiletries (max should be False
     — floor only, no ceiling), fuel (per_vehicle/watch_per_adult/
     non_watch_per_adult/watch_per_vehicle all wrong), public_transport
     (min flag and adult_1 base rate wrong).

  4. Three "Home and Content" rows (ground_rent_service_charges,
     mortgage_endowment, appliance_furniture_rental) and three
     "Communication and Leisure" rows (gifts, pocket_money,
     newspapers_magazines_stationery_and_postage) don't exist in production
     at all — traced to case-assessment-backend migrations 0053/0055 doing
     GuidelineCategory.objects.get(name='Home and Content' /
     'Communication and Leisure') AFTER 0033 had already renamed those
     categories to the plural form, so the lookups raised DoesNotExist and
     were silently skipped (print + continue). Deleting these 6 rows here
     per explicit instruction to match live production exactly, bugs
     included — case-assessment-backend has its own bug to fix separately;
     these should be re-added once it is.

All field values below were read directly off the production JSON payload,
not re-derived — see the assistant transcript this migration was authored
from for the source paste.
"""
from decimal import Decimal
from django.db import migrations, transaction


# (slug, {field: new_value}) — only the fields that actually differ from
# what 0073 set are listed; anything else on the row is left untouched.
FIELD_FIXES = [
    ('home_phone_internet', {'min': True, 'max': False}),
    ('mobile_phones', {'min': True, 'max': False, 'adult_1': '0.00', 'adult_2': '0.00'}),
    ('hairdressing', {'min': False, 'max': False, 'adult_1': '0.00', 'adult_2': '0.00'}),
    ('hobbies', {
        'max': False,
        'adult_1_child_1': '40.00', 'adult_1_child_2': '50.00', 'adult_1_child_3': '60.00',
        'adult_1_child_4': '70.00', 'adult_1_child_5': '80.00',
        'adult_2_child_1': '50.00', 'adult_2_child_2': '60.00', 'adult_2_child_3': '70.00',
        'adult_2_child_4': '80.00', 'adult_2_child_5': '90.00',
    }),
    ('mot_spares', {
        'adult_1_child_1': '20.00', 'adult_1_child_2': '20.00', 'adult_1_child_3': '20.00',
        'adult_1_child_4': '20.00', 'adult_1_child_5': '20.00',
        'adult_2_child_1': '20.00', 'adult_2_child_2': '20.00', 'adult_2_child_3': '20.00',
        'adult_2_child_4': '20.00', 'adult_2_child_5': '20.00',
    }),
    ('fuel', {
        'per_vehicle': '200.00', 'watch_per_adult': '200.00',
        'non_watch_per_adult': '280.00', 'watch_per_vehicle': '200.00',
    }),
    ('public_transport', {'min': False, 'adult_1': '0.00'}),
    ('food_milk_groceries', {
        'max': False,
        'adult_1_child_1': '220.00', 'adult_1_child_2': '275.00', 'adult_1_child_3': '330.00',
        'adult_1_child_4': '385.00', 'adult_1_child_5': '440.00',
        'adult_2_child_1': '275.00', 'adult_2_child_2': '330.00', 'adult_2_child_3': '385.00',
        'adult_2_child_4': '440.00', 'adult_2_child_5': '495.00',
    }),
    ('laundry_dry_cleaning', {
        'max': False,
        'adult_1_child_1': '15.00', 'adult_1_child_2': '20.00', 'adult_1_child_3': '25.00',
        'adult_1_child_4': '30.00', 'adult_1_child_5': '35.00',
        'adult_2_child_1': '25.00', 'adult_2_child_2': '30.00', 'adult_2_child_3': '35.00',
        'adult_2_child_4': '40.00', 'adult_2_child_5': '45.00',
    }),
    ('clothing_footwear', {
        'max': False,
        'adult_1_child_1': '40.00', 'adult_1_child_2': '55.00', 'adult_1_child_3': '70.00',
        'adult_1_child_4': '85.00', 'adult_1_child_5': '100.00',
        'adult_2_child_1': '65.00', 'adult_2_child_2': '80.00', 'adult_2_child_3': '95.00',
        'adult_2_child_4': '110.00', 'adult_2_child_5': '125.00',
    }),
    ('toiletries', {
        'max': False,
        'adult_1_child_1': '15.00', 'adult_1_child_2': '20.00', 'adult_1_child_3': '25.00',
        'adult_1_child_4': '30.00', 'adult_1_child_5': '35.00',
        'adult_2_child_1': '25.00', 'adult_2_child_2': '30.00', 'adult_2_child_3': '35.00',
        'adult_2_child_4': '40.00', 'adult_2_child_5': '45.00',
    }),
    ('health_minimum', {
        'adult_1_child_1': '10.00', 'adult_1_child_2': '10.00', 'adult_1_child_3': '10.00',
        'adult_1_child_4': '10.00', 'adult_1_child_5': '10.00',
        'adult_2_child_1': '20.00', 'adult_2_child_2': '20.00', 'adult_2_child_3': '20.00',
        'adult_2_child_4': '20.00', 'adult_2_child_5': '20.00',
    }),
]

# Category renames: (old_name, new_name)
CATEGORY_RENAMES = [
    ('Home and Content', 'Home and Contents'),
    ('Communication and Leisure', 'Communications and Leisure'),
]

# Rows to delete because they don't exist in production (see docstring #4).
# Full original data (as inserted by 0073) kept here so backwards() can
# recreate them exactly.
ZERO_NUMERIC = {f: '0.00' for f in [
    'adult_1', 'adult_2',
    'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
    'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
    'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
    'child_under_16', 'child_16_18',
    'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
    'one_adult_cap', 'two_adults_cap',
]}

ROWS_TO_DELETE = [
    {
        'category': 'ground_rent_service_charges', 'label': 'Ground Rent & Service Charges',
        'category_group_name': 'Home and Contents', 'sort_order': 4, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': 'AMBER',
        'notes': 'Leasehold cost, not tenancy rent. Expenses_List_ismael.xlsx: Required=Yes',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
    {
        'category': 'mortgage_endowment', 'label': 'Mortgage Endowment',
        'category_group_name': 'Home and Contents', 'sort_order': 5, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': 'AMBER',
        'notes': 'Expenses_List_ismael.xlsx: Required=Yes',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
    {
        'category': 'appliance_furniture_rental', 'label': 'Appliance & Furniture Rental',
        'category_group_name': 'Home and Contents', 'sort_order': 6, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': '',
        'notes': 'Expenses_List_ismael.xlsx: Required=No',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
    {
        'category': 'gifts', 'label': 'Gifts',
        'category_group_name': 'Communications and Leisure', 'sort_order': 4, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': '',
        'notes': 'Expenses_List_ismael.xlsx: Required=No',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
    {
        'category': 'pocket_money', 'label': 'Pocket Money',
        'category_group_name': 'Communications and Leisure', 'sort_order': 5, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': '',
        'notes': 'Expenses_List_ismael.xlsx: Required=No',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
    {
        'category': 'newspapers_magazines_stationery_and_postage',
        'label': 'Newspapers Magazines Stationery and Postage',
        'category_group_name': 'Communications and Leisure', 'sort_order': 6, 'min': False, 'max': False,
        'formula': '', 'below_action': 'RED', 'above_action': '', 'mismatch_action': '',
        'notes': 'Expenses_List_ismael.xlsx: Required=No',
        'aryza_aliases': '', **ZERO_NUMERIC,
    },
]

# Snapshot of the pre-fix field values for every slug touched by FIELD_FIXES,
# so backwards() can restore exactly what 0073 originally set — not just flip
# booleans back, since several rows have >10 numeric fields changing together.
FIELD_FIXES_REVERSE = [
    ('home_phone_internet', {'min': False, 'max': True}),
    ('mobile_phones', {'min': False, 'max': True, 'adult_1': '30.00', 'adult_2': '40.00'}),
    ('hairdressing', {'min': True, 'max': True, 'adult_1': '10.00', 'adult_2': '20.00'}),
    ('hobbies', {
        'max': True,
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('mot_spares', {
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('fuel', {
        'per_vehicle': '0.00', 'watch_per_adult': '0.00',
        'non_watch_per_adult': '0.00', 'watch_per_vehicle': '170.00',
    }),
    ('public_transport', {'min': True, 'adult_1': '50.00'}),
    ('food_milk_groceries', {
        'max': True,
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('laundry_dry_cleaning', {
        'max': True,
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('clothing_footwear', {
        'max': True,
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('toiletries', {
        'max': True,
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
    ('health_minimum', {
        'adult_1_child_1': '0.00', 'adult_1_child_2': '0.00', 'adult_1_child_3': '0.00',
        'adult_1_child_4': '0.00', 'adult_1_child_5': '0.00',
        'adult_2_child_1': '0.00', 'adult_2_child_2': '0.00', 'adult_2_child_3': '0.00',
        'adult_2_child_4': '0.00', 'adult_2_child_5': '0.00',
    }),
]


def _cast(field, value):
    """min/max are booleans; everything else in these dicts is a decimal string."""
    if field in ('min', 'max'):
        return bool(value)
    return Decimal(value)


def _apply_fixes(ExpenditureGuideline, fixes):
    for slug, changes in fixes:
        try:
            g = ExpenditureGuideline.objects.get(category=slug)
        except ExpenditureGuideline.DoesNotExist:
            print(f"ERROR: ExpenditureGuideline '{slug}' not found — skipping fix")
            continue
        for field, value in changes.items():
            setattr(g, field, _cast(field, value))
        g.save(update_fields=list(changes.keys()))


def forwards(apps, schema_editor):
    GuidelineCategory = apps.get_model('debt_app', 'GuidelineCategory')
    ExpenditureGuideline = apps.get_model('debt_app', 'ExpenditureGuideline')

    with transaction.atomic():
        # 1. Rename categories back to production's plural forms.
        for old_name, new_name in CATEGORY_RENAMES:
            try:
                cat = GuidelineCategory.objects.get(name=old_name)
                cat.name = new_name
                cat.save(update_fields=['name'])
            except GuidelineCategory.DoesNotExist:
                print(f"ERROR: GuidelineCategory '{old_name}' not found — skipping rename to '{new_name}'")

        # 2. Fix flags/values that don't match production.
        _apply_fixes(ExpenditureGuideline, FIELD_FIXES)

        # 3. Delete the 6 rows production doesn't have.
        for row in ROWS_TO_DELETE:
            deleted, _ = ExpenditureGuideline.objects.filter(category=row['category']).delete()
            if not deleted:
                print(f"  ok  '{row['category']}' already absent — nothing to delete")


def backwards(apps, schema_editor):
    GuidelineCategory = apps.get_model('debt_app', 'GuidelineCategory')
    ExpenditureGuideline = apps.get_model('debt_app', 'ExpenditureGuideline')

    with transaction.atomic():
        # Reverse order of forwards().

        # 3. Recreate the 6 deleted rows exactly as 0073 originally inserted them.
        for row in ROWS_TO_DELETE:
            if ExpenditureGuideline.objects.filter(category=row['category']).exists():
                continue
            try:
                group = GuidelineCategory.objects.get(name=row['category_group_name'])
            except GuidelineCategory.DoesNotExist:
                print(f"ERROR: GuidelineCategory '{row['category_group_name']}' not found — "
                      f"skipping recreation of '{row['category']}'")
                continue
            field_kwargs = {
                k: (Decimal(v) if k not in ('category', 'label', 'formula', 'below_action',
                                             'above_action', 'mismatch_action', 'notes',
                                             'aryza_aliases', 'sort_order', 'min', 'max')
                    else v)
                for k, v in row.items()
                if k != 'category_group_name'
            }
            field_kwargs['min'] = bool(row['min'])
            field_kwargs['max'] = bool(row['max'])
            ExpenditureGuideline.objects.create(category_group=group, **field_kwargs)

        # 2. Revert flags/values to what 0073 originally set.
        _apply_fixes(ExpenditureGuideline, FIELD_FIXES_REVERSE)

        # 1. Revert category renames.
        for old_name, new_name in CATEGORY_RENAMES:
            try:
                cat = GuidelineCategory.objects.get(name=new_name)
                cat.name = old_name
                cat.save(update_fields=['name'])
            except GuidelineCategory.DoesNotExist:
                print(f"ERROR: GuidelineCategory '{new_name}' not found — skipping revert to '{old_name}'")


class Migration(migrations.Migration):
    dependencies = [
        ('debt_app', '0073_sync_sfs_guidelines_from_case_assessment'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
