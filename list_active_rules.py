#!/usr/bin/env python
import os
import django
from pathlib import Path

# Set up Django environment
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import GlobalCriteria, CreditorCriteria, CouncilRule

output_file = BASE_DIR / 'active_rules_list.txt'

with open(output_file, 'w', encoding='utf-8') as f:
    f.write("=" * 100 + "\n")
    f.write("ACTIVE GLOBAL RULES\n")
    f.write("=" * 100 + "\n")
    active_global = GlobalCriteria.objects.filter(is_active=True).order_by('criteria_set', 'rule_key')
    f.write(f"Count: {active_global.count()}\n")
    for rule in active_global:
        f.write(f"  - [{rule.criteria_set}] {rule.rule_key}: {rule.rule_name} (Severity: {rule.severity})\n")

    f.write("\n" + "=" * 100 + "\n")
    f.write("ACTIVE CREDITOR CRITERIA\n")
    f.write("=" * 100 + "\n")
    active_creditors = CreditorCriteria.objects.filter(is_active=True).order_by('creditor_name')
    f.write(f"Count: {active_creditors.count()}\n")
    for creditor in active_creditors:
        f.write(f"  - {creditor.creditor_name} (Status: {creditor.status}, Rep: {creditor.representative})\n")

    f.write("\n" + "=" * 100 + "\n")
    f.write("COUNCIL RULES\n")
    f.write("=" * 100 + "\n")
    councils = CouncilRule.objects.all().order_by('council_name')
    f.write(f"Count: {councils.count()}\n")
    for council in councils:
        f.write(f"  - {council.council_name} (Status: {council.status})\n")

print(f"Active rules list written to: {output_file}")
