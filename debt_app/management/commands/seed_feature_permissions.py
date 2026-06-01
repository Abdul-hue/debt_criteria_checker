"""
Management command to seed DepartmentFeaturePermission records.

Creates READ permission level for each department for all permission-enabled features.
Admins can then manually change to WRITE permission in the Django admin interface.
"""

from django.core.management.base import BaseCommand
from debt_app.models import Department, DepartmentFeaturePermission


class Command(BaseCommand):
    help = 'Seeds DepartmentFeaturePermission records with default READ access for all departments'

    PERMISSION_FEATURES = [
        'general_creditors',
        'representative_creditors',
        'global_rules',
        'councils',
        'dividends',
        'sfs_guidelines',
    ]

    DEFAULT_PERMISSION_LEVEL = 'READ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all existing permission records before seeding',
        )

    def handle(self, *args, **options):
        if options['reset']:
            count, _ = DepartmentFeaturePermission.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Deleted {count} existing permission records.')
            )

        departments = Department.objects.filter(is_active=True)
        created_count = 0
        skipped_count = 0

        for dept in departments:
            for feature_key in self.PERMISSION_FEATURES:
                perm, created = DepartmentFeaturePermission.objects.get_or_create(
                    department=dept,
                    feature_key=feature_key,
                    defaults={'permission_level': self.DEFAULT_PERMISSION_LEVEL}
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        f'✓ Created {dept.name} → {feature_key}: {self.DEFAULT_PERMISSION_LEVEL}'
                    )
                else:
                    skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Seeding complete: {created_count} created, {skipped_count} already exist.'
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f'\n⚠ Next steps:\n'
                f'  1. Visit the Django admin (e.g., http://localhost:5173/admin/debt_app/departmentfeaturepermission/)\n'
                f'  2. For each department, set the permission level to WRITE for features they should edit\n'
                f'  3. Leave as READ for view-only features'
            )
        )
