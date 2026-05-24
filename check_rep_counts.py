import os
import django
import sys
from pathlib import Path

# Setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import CreditorCriteria

with_rep = CreditorCriteria.objects.exclude(representative='NONE').count()
without_rep = CreditorCriteria.objects.filter(representative='NONE').count()

print(f"With Rep: {with_rep}")
print(f"Without Rep: {without_rep}")
print(f"Total: {with_rep + without_rep}")
