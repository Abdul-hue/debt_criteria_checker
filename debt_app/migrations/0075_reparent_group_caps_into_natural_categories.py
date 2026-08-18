"""
Move the 3 SFS group-cap rows out of the standalone "Group Caps" category
and into the natural category each one actually caps, matching production
case-assessment-tool exactly (verified against its live
GET /api/assessments/guideline-categories/ payload):

    comms_and_leisure_group -> Communications and Leisure  (sort_order 1)
    housekeep_group         -> Food and Housekeeping        (sort_order 2)
    personal_group          -> Personal Costs                (sort_order 3)

Production has no standalone "Group Caps" category at all — these three
group-maximum rows have always lived inside their own category there, right
next to the line items they cap. debt_criteria_checker split them out into a
separate category at some point (0042/0049 seed history), which is why the
SFSGuidelinesPage.jsx "SFS group max" badge/column — which looks for one of
these slugs INSIDE each category's own guideline list — only ever showed up
under "Group Caps" instead of under Communications and Leisure / Food and
Housekeeping / Personal Costs individually. No frontend change needed: once
category_group is corrected here, the existing per-category badge logic
(SFS_GROUP_SLUGS lookup in cat.guidelines) picks it up automatically.

Deletes the now-empty "Group Caps" category once its 3 rows are moved out.
"""
from django.db import migrations, transaction

# (slug, target_category_name, new_sort_order) — sort_order values copied
# verbatim from production's live data.
MOVES = [
    ('comms_and_leisure_group', 'Communications and Leisure', 1),
    ('housekeep_group', 'Food and Housekeeping', 2),
    ('personal_group', 'Personal Costs', 3),
]

# Reverse: put them back under "Group Caps" with their original sort_order
# (1, 2, 3 respectively, matching the order 0073 originally inserted them in).
MOVES_REVERSE = [
    ('comms_and_leisure_group', 'Group Caps', 1),
    ('housekeep_group', 'Group Caps', 2),
    ('personal_group', 'Group Caps', 3),
]

GROUP_CAPS_SORT_ORDER = 15


def forwards(apps, schema_editor):
    GuidelineCategory = apps.get_model('debt_app', 'GuidelineCategory')
    ExpenditureGuideline = apps.get_model('debt_app', 'ExpenditureGuideline')

    with transaction.atomic():
        for slug, target_category_name, sort_order in MOVES:
            try:
                guideline = ExpenditureGuideline.objects.get(category=slug)
            except ExpenditureGuideline.DoesNotExist:
                print(f"ERROR: ExpenditureGuideline '{slug}' not found — skipping move")
                continue
            try:
                target = GuidelineCategory.objects.get(name=target_category_name)
            except GuidelineCategory.DoesNotExist:
                print(f"ERROR: GuidelineCategory '{target_category_name}' not found — skipping move of '{slug}'")
                continue
            guideline.category_group = target
            guideline.sort_order = sort_order
            guideline.save(update_fields=['category_group', 'sort_order'])

        # Delete "Group Caps" only if it's now empty (all 3 rows moved out
        # successfully) — never delete a category that still holds guidelines.
        try:
            group_caps = GuidelineCategory.objects.get(name='Group Caps')
            remaining = ExpenditureGuideline.objects.filter(category_group=group_caps).count()
            if remaining == 0:
                group_caps.delete()
            else:
                print(f"  ok  'Group Caps' still has {remaining} row(s) — left in place, not deleted")
        except GuidelineCategory.DoesNotExist:
            print("  ok  'Group Caps' already absent — nothing to delete")


def backwards(apps, schema_editor):
    GuidelineCategory = apps.get_model('debt_app', 'GuidelineCategory')
    ExpenditureGuideline = apps.get_model('debt_app', 'ExpenditureGuideline')

    with transaction.atomic():
        # Recreate "Group Caps" if it's gone.
        group_caps, _ = GuidelineCategory.objects.get_or_create(
            name='Group Caps',
            defaults={'sort_order': GROUP_CAPS_SORT_ORDER, 'upper_cap': None},
        )

        for slug, target_category_name, sort_order in MOVES_REVERSE:
            try:
                guideline = ExpenditureGuideline.objects.get(category=slug)
            except ExpenditureGuideline.DoesNotExist:
                print(f"ERROR: ExpenditureGuideline '{slug}' not found — skipping revert")
                continue
            guideline.category_group = group_caps
            guideline.sort_order = sort_order
            guideline.save(update_fields=['category_group', 'sort_order'])


class Migration(migrations.Migration):
    dependencies = [
        ('debt_app', '0074_fix_sfs_guideline_sync_from_production'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
