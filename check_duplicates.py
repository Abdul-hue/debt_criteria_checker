import os
import django
import sys
from pathlib import Path
from django.db.models import Count

# Setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

duplicates = CreditorCriteria.objects.values('creditor_name').annotate(name_count=Count('id')).filter(name_count__gt=1)

print(f"Total Unique Names: {CreditorCriteria.objects.values('creditor_name').distinct().count()}")
print(f"Total Records: {CreditorCriteria.objects.count()}")

if duplicates.exists():
    print("\nDuplicate names found:")
    for d in duplicates[:10]:
        print(f"  - {d['creditor_name']}: {d['name_count']} times")
else:
    print("\nNo duplicate names found.")
