import os
import django
import sys
from pathlib import Path

# Setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

all_creditors = CreditorCriteria.objects.all().order_by('source_sheet', 'creditor_name')
with open("dump_all_creditors.txt", "w", encoding="utf-8") as f:
    f.write(f"Total: {all_creditors.count()}\n\n")
    current_source = None
    for c in all_creditors:
        if c.source_sheet != current_source:
            current_source = c.source_sheet
            f.write(f"\n--- SOURCE: {current_source} ---\n")
        f.write(f"  - {c.creditor_name}\n")

print("Dump complete: dump_all_creditors.txt")
