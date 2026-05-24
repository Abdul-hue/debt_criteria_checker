import os
import django
import sys
from pathlib import Path
from django.db.models.functions import Lower

# Setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

distinct_sources = CreditorCriteria.objects.values_list('source_sheet', flat=True).distinct()
print(f"Distinct sources: {list(distinct_sources)}")

source_counts = {}
for s in distinct_sources:
    source_counts[s] = CreditorCriteria.objects.filter(source_sheet=s).count()

print("\nCounts:")
for s, count in source_counts.items():
    print(f"  {s}: {count}")
