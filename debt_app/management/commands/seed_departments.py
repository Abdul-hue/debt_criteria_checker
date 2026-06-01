from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from debt_app.models import Department, UserProfile, DepartmentFeatureAccess

ALL_FEATURES = [
    'general_creditors',
    'representative_creditors',
    'global_rules',
    'councils',
    'dividends',
    'sfs_guidelines',
    'run_assessment',
    'decisions',
    'evidence',
    'user_management',
]

LEAD_GEN_ENABLED = {
    'general_creditors',
    'representative_creditors',
    'global_rules',
    'councils',
    'dividends',
}


class Command(BaseCommand):
    help = "Seed default departments and assign all existing users to the Default department."

    def handle(self, *args, **options):
        default_dept, created = Department.objects.get_or_create(
            slug='default',
            defaults={
                'name': 'Default',
                'description': 'Default department — sees all rules. Assigned to all existing users.',
                'is_active': True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created department: Default"))
        else:
            self.stdout.write("Department already exists: Default")

        lead_gen_dept, created = Department.objects.get_or_create(
            slug='lead-generation',
            defaults={
                'name': 'Lead Generation',
                'description': 'Lead Generation department — rule visibility assigned by admin.',
                'is_active': True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created department: Lead Generation"))
        else:
            self.stdout.write("Department already exists: Lead Generation")

        # Seed DepartmentFeatureAccess for Default (all enabled)
        for key in ALL_FEATURES:
            obj, created = DepartmentFeatureAccess.objects.get_or_create(
                department=default_dept,
                feature_key=key,
                defaults={'is_enabled': True},
            )
            if created:
                self.stdout.write(f"  Created feature access: Default → {key} = True")

        # Seed DepartmentFeatureAccess for Lead Generation
        for key in ALL_FEATURES:
            is_enabled = key in LEAD_GEN_ENABLED
            obj, created = DepartmentFeatureAccess.objects.get_or_create(
                department=lead_gen_dept,
                feature_key=key,
                defaults={'is_enabled': is_enabled},
            )
            if created:
                self.stdout.write(f"  Created feature access: Lead Generation → {key} = {is_enabled}")

        assigned = 0
        for user in User.objects.all():
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'department': default_dept},
            )
            if not created and profile.department is None:
                profile.department = default_dept
                profile.save(update_fields=['department'])
                assigned += 1
            elif created:
                assigned += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned {assigned} user(s) to the Default department via UserProfile."
            )
        )
