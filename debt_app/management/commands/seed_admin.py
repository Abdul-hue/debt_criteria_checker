from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Create a default admin user'

    def handle(self, *args, **options):
        email = 'admin@test.com'
        password = 'password123'
        
        user = User.objects.filter(email=email).first()
        if not user:
            User.objects.create_superuser(
                username='admin',
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created admin user: {email}'))
        else:
            user.set_password(password)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully updated admin user password and status: {email}'))
