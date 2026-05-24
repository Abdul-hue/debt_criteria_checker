from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a default admin user'

    def handle(self, *args, **options):
        email = 'admin@test.com'
        password = 'password123'
        
        if not User.objects.filter(email=email).exists():
            User.objects.create_superuser(
                username='admin',
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created admin user: {email}'))
        else:
            self.stdout.write(self.style.WARNING(f'Admin user with email {email} already exists.'))
