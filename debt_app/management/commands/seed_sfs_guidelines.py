"""
Seed SFS expenditure guideline categories and baseline rows.

Usage (hardcoded defaults):
    python manage.py seed_sfs_guidelines

Usage (import from exported JSON):
    python manage.py seed_sfs_guidelines --from-file=path/to/sfs_guidelines_export.json

Re-running is safe — uses update_or_create throughout.
"""
import json
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from debt_app.models import GuidelineCategory, ExpenditureGuideline


NUMERIC_FIELDS = [
    'adult_1', 'adult_2',
    'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
    'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
    'per_child', 'per_vehicle', 'first_adult', 'additional_adult',
    'child_under_16', 'child_16_18',
    'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
    'one_adult_cap', 'two_adults_cap',
]

CATEGORIES = [
    {'name': 'Home and Content',          'sort_order': 1,  'upper_cap': None},
    {'name': 'Utilities',                  'sort_order': 2,  'upper_cap': None},
    {'name': 'Water',                      'sort_order': 3,  'upper_cap': None},
    {'name': 'Communication and Leisure', 'sort_order': 4,  'upper_cap': None},
    {'name': 'Transport and Travel',       'sort_order': 5,  'upper_cap': None},
    {'name': 'Food and Housekeeping',      'sort_order': 6,  'upper_cap': None},
    {'name': 'Pensions and Insurances',    'sort_order': 7,  'upper_cap': None},
    {'name': 'Personal Costs',             'sort_order': 8,  'upper_cap': None},
    {'name': 'Care and Health Costs',      'sort_order': 9,  'upper_cap': None},
    {'name': 'School Costs',               'sort_order': 10, 'upper_cap': None},
    {'name': 'Professional Costs',         'sort_order': 11, 'upper_cap': None},
    {'name': 'Other',                      'sort_order': 12, 'upper_cap': None},
    {'name': 'Group Caps',                 'sort_order': 13, 'upper_cap': None},
]

GUIDELINES = [
    # (category slug, label, category_group_name, sort_order)
    ('rent',                      'Rent',                               'Home and Content',       1),
    ('mortgage_secured_loans',    'Mortgage / Secured Loans',           'Home and Content',       2),
    ('council_tax',               'Council Tax',                        'Home and Content',       3),
    ('tv_licence',                'TV Licence',                         'Home and Content',       4),
    ('gas',                       'Gas',                                'Utilities',              1),
    ('electric',                  'Electric',                           'Utilities',              2),
    ('water',                     'Water',                              'Water',                  1),
    ('home_phone_internet',       'Home Phone / Internet',              'Communication and Leisure', 1),
    ('mobile_phones',             'Mobile Phones',                      'Communication and Leisure', 2),
    ('food_milk_groceries',       'Food, Milk & Groceries',             'Food and Housekeeping',  1),
    ('cleaning_toiletries',       'Cleaning & Toiletries',              'Food and Housekeeping',  2),
    ('clothing_footwear',         'Clothing & Footwear',                'Personal Costs',         1),
    ('childcare',                 'Childcare',                          'Care and Health Costs',  1),
    ('transport_public',          'Public Transport',                   'Transport and Travel',   1),
    ('fuel',                      'Fuel',                               'Transport and Travel',   2),
    ('car_insurance',             'Car Insurance',                      'Transport and Travel',   3),
    ('health_minimum',            'Health (Minimum)',                   'Care and Health Costs',  2),
    ('prescriptions_dentistry',   'Prescriptions & Dentistry',          'Care and Health Costs',  3),
    ('professional_courses',      'Professional Courses',               'Professional Costs',     1),
    ('other_essential_costs',     'Other Essential Costs',              'Other',                  1),
]


class Command(BaseCommand):
    help = 'Seeds SFS expenditure guideline categories and baseline rows'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-file',
            dest='from_file',
            default=None,
            help='Path to a JSON file exported by case-assessment export_sfs_guidelines command',
        )

    def handle(self, *args, **options):
        if options['from_file']:
            self._seed_from_file(options['from_file'])
        else:
            self._seed_hardcoded()

    # ── File-based import ────────────────────────────────────────────────────

    def _seed_from_file(self, file_path):
        try:
            with open(file_path, encoding='utf-8') as f:
                rows = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON in {file_path}: {exc}')

        if not isinstance(rows, list):
            raise CommandError('Expected a JSON array at the top level')

        created_count = 0
        updated_count = 0

        for row in rows:
            group_name = row.get('category_group_name', '').strip()
            group = None
            if group_name:
                group, _ = GuidelineCategory.objects.get_or_create(
                    name=group_name,
                    defaults={'sort_order': 0},
                )

            defaults = {
                'label': row.get('label', ''),
                'category_group': group,
                'sort_order': int(row.get('sort_order', 0)),
                'max': bool(row.get('max', False)),
                'min': bool(row.get('min', False)),
                'formula': row.get('formula', ''),
                'below_action': row.get('below_action', ''),
                'above_action': row.get('above_action', ''),
                'mismatch_action': row.get('mismatch_action', ''),
                'notes': row.get('notes', ''),
            }

            for field in NUMERIC_FIELDS:
                raw = row.get(field, '0.00')
                try:
                    defaults[field] = Decimal(str(raw))
                except (InvalidOperation, TypeError):
                    defaults[field] = Decimal('0.00')

            _, created = ExpenditureGuideline.objects.update_or_create(
                category=row['category'],
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Updated {updated_count} guidelines, created {created_count} new ones '
            f'({updated_count + created_count} total from {len(rows)} rows in file)'
        ))

    # ── Hardcoded fallback ───────────────────────────────────────────────────

    def _seed_hardcoded(self):
        cat_map = {}
        for cat_data in CATEGORIES:
            cat, created = GuidelineCategory.objects.update_or_create(
                name=cat_data['name'],
                defaults={
                    'sort_order': cat_data['sort_order'],
                    'upper_cap': cat_data['upper_cap'],
                },
            )
            cat_map[cat_data['name']] = cat
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb} category: {cat.name}')

        self.stdout.write(self.style.SUCCESS(f'Categories: {len(CATEGORIES)} processed'))

        for slug, label, group_name, sort_order in GUIDELINES:
            group = cat_map.get(group_name)
            _, created = ExpenditureGuideline.objects.update_or_create(
                category=slug,
                defaults={
                    'label': label,
                    'category_group': group,
                    'sort_order': sort_order,
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(f'  {verb} guideline: {label} ({slug})')

        self.stdout.write(self.style.SUCCESS(f'Guidelines: {len(GUIDELINES)} processed'))
        self.stdout.write(self.style.SUCCESS('seed_sfs_guidelines complete'))
