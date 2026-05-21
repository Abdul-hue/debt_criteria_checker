import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorCriteria
from collections import defaultdict

res = defaultdict(list)
for c in CreditorCriteria.objects.all():
    res[c.representative].append(c.creditor_name)

with open('creditor_groups.md', 'w', encoding='utf-8') as f:
    f.write("# Creditors by Representative\n\n")
    for rep, names in res.items():
        rep_name = rep if rep else 'NONE'
        f.write(f"## {rep_name}\n")
        for name in sorted(list(set(names))):
            f.write(f"- {name}\n")
        f.write("\n")
