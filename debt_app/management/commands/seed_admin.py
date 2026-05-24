from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a default admin user'

    def handle(self, *args, **options):
        email = 'admin@test.com'
        password = 'admin123'
        
        # Completely delete and recreate to ensure no hashing/state issues
        User.objects.filter(email=email).delete()
        User.objects.filter(username='admin').delete()
        
        User.objects.create_superuser(
            username='admin',
            email=email,
            password=password,
            is_active=True,
            is_staff=True
        )
        self.stdout.write(self.style.SUCCESS(f'DELETED and RECREATED admin user: {email} with password: {password}'))
