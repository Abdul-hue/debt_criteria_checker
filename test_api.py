#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from debt_app.views.dept_views import DepartmentPermissionsView
from debt_app.models import Department
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

# Create an admin user and get a token
admin_user = User.objects.filter(username='admin').first()
if not admin_user:
    admin_user = User.objects.create_superuser(username='admin', email='admin@test.com', password='admin')

refresh = RefreshToken.for_user(admin_user)
access_token = str(refresh.access_token)

# Create request
factory = APIRequestFactory()

# Get Lead Generation department
lg_dept = Department.objects.get(name='Lead Generation')

# Simulate GET request to permissions endpoint
request = factory.get(f'/api/v1/criteria/departments/{lg_dept.id}/permissions/')
request.META['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'

from rest_framework_simplejwt.authentication import JWTAuthentication
auth = JWTAuthentication()
authenticated = auth.authenticate(request)
if authenticated:
    request.user = authenticated[0]

# Call the view
view = DepartmentPermissionsView.as_view()
response = view(request, pk=lg_dept.id)

print("=" * 60)
print(f"GET /departments/{lg_dept.id}/permissions/")
print("=" * 60)
print(f"Status Code: {response.status_code}")
print(f"\nResponse Data:")
import json
print(json.dumps(response.data, indent=2))
