import os
import django
import sys
from pathlib import Path
from collections import Counter

# Setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

print(f"Total Creditors: {CreditorCriteria.objects.count()}")
sources = CreditorCriteria.objects.values_list('source_sheet', flat=True)
counts = Counter(sources)

print("\nCounts by source_sheet:")
for source, count in counts.items():
    print(f"  {source}: {count}")

# Check if any have 'GENERAL_CREDITOR' but are duplicates or something?
gen_creditors = CreditorCriteria.objects.filter(source_sheet='GENERAL_CREDITOR').order_by('creditor_name')
print(f"\nFirst 10 General Creditors:")
for c in gen_creditors[:10]:
    print(f"  - {c.creditor_name}")
