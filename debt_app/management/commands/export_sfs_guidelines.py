"""
Export SFS expenditure guidelines to JSON for transfer between environments.

Usage:
    python manage.py export_sfs_guidelines
    python manage.py export_sfs_guidelines --output=sfs_export.json

Import the output on another server with:
    python manage.py seed_sfs_guidelines --from-file=sfs_export.json
"""
import json
from decimal import Decimal
from django.core.management.base import BaseCommand
from debt_app.models import ExpenditureGuideline


NUMERIC_FIELDS = [
    'adult_1', 'adult_2',
    'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
    'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
    'per_child', 'per_vehicle', 'first_adult', 'additional_adult',
    'child_under_16', 'child_16_18',
    'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
    'one_adult_cap', 'two_adults_cap',
]


class Command(BaseCommand):
    help = 'Export SFS expenditure guidelines to JSON (importable via seed_sfs_guidelines --from-file)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            dest='output',
            default=None,
            help='Path to write JSON output (default: print to stdout)',
        )

    def handle(self, *args, **options):
        guidelines = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order'
        )

        rows = []
        for g in guidelines:
            row = {
                'category': g.category,
                'label': g.label,
                'category_group_name': g.category_group.name if g.category_group else '',
                'sort_order': g.sort_order,
                'min': g.min,
                'max': g.max,
                'formula': g.formula or '',
                'below_action': g.below_action or '',
                'above_action': g.above_action or '',
                'mismatch_action': g.mismatch_action or '',
                'notes': g.notes or '',
            }
            for field in NUMERIC_FIELDS:
                value = getattr(g, field, None)
                row[field] = str(value) if value is not None else '0.00'
            rows.append(row)

        output = json.dumps(rows, indent=2)

        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as f:
                f.write(output)
            self.stdout.write(self.style.SUCCESS(
                f'Exported {len(rows)} guidelines to {options["output"]}'
            ))
        else:
            self.stdout.write(output)
            self.stderr.write(self.style.SUCCESS(f'Exported {len(rows)} guidelines'))
