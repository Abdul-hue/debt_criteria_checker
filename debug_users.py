from django.contrib.auth.models import User
import sys

def check_users():
    users = User.objects.all()
    print(f"Total users: {users.count()}")
    for user in users:
        print(f"Username: {user.username}, Email: {user.email}, Is Superuser: {user.is_superuser}, Is Active: {user.is_active}")
        # Test password check for admin@test.com if it exists
        if user.email == 'admin@test.com':
            is_correct = user.check_password('password123')
            print(f"Password 'password123' check: {is_correct}")

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
    django.setup()
    check_users()
