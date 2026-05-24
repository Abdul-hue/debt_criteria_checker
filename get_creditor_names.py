#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria

for term in ['link financial', 'shop direct', 'jd williams', 'n brown']:
    rows = list(CreditorCriteria.objects.filter(
        creditor_name__icontains=term, is_active=True
    ).values_list('creditor_name', flat=True))
    print(f'{term}: {rows}')
