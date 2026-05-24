#!/usr/bin/env python
"""Check if NatWest and Lloyds exist in multiple representatives."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

# Check NatWest in both reps
print('=== NatWest ENTRIES ===')
rows = list(CreditorCriteria.objects.filter(creditor_name__icontains='natwest').values('creditor_name', 'representative'))
for r in sorted(rows, key=lambda x: x['representative']):
    print(f'  {r["creditor_name"]:<50} | {r["representative"]}')

# Check Lloyds in both reps
print('\n=== Lloyds ENTRIES ===')
rows = list(CreditorCriteria.objects.filter(creditor_name__icontains='lloyds').values('creditor_name', 'representative'))
for r in sorted(rows, key=lambda x: x['representative']):
    print(f'  {r["creditor_name"]:<50} | {r["representative"]}')

# Check MBNA
print('\n=== MBNA ENTRIES ===')
rows = list(CreditorCriteria.objects.filter(creditor_name__icontains='mbna').values('creditor_name', 'representative'))
for r in sorted(rows, key=lambda x: x['representative']):
    print(f'  {r["creditor_name"]:<50} | {r["representative"]}')

# Check Shop Direct / JD Williams
print('\n=== SHOP DIRECT / JD WILLIAMS ENTRIES ===')
rows = list(CreditorCriteria.objects.filter(creditor_name__icontains='shop').values('creditor_name', 'representative'))
rows.extend(list(CreditorCriteria.objects.filter(creditor_name__icontains='jd').values('creditor_name', 'representative')))
for r in sorted(rows, key=lambda x: x['representative']):
    print(f'  {r["creditor_name"]:<50} | {r["representative"]}')
