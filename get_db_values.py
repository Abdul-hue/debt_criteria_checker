#!/usr/bin/env python
"""Query DB for exact creditor names."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

# Get all active creditors
rows = list(CreditorCriteria.objects.filter(
    is_active=True
).values('creditor_name', 'representative').order_by('representative'))

print("=== ALL ACTIVE CREDITORS BY REPRESENTATIVE ===")
for r in rows:
    print(f"  {r['creditor_name']:<50} | {r['representative']}")

print("\n=== EVOLVE CREDITORS SPECIFICALLY ===")
evolve_rows = list(CreditorCriteria.objects.filter(
    is_active=True,
    representative='EVOLVE'
).values('creditor_name'))
for r in evolve_rows:
    print(f"  {r['creditor_name']}")
