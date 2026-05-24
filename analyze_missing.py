#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import GlobalCriteria

# Documented items from markdown
markdown_docs = {
    'TIG': {
        'Core': ['Min debt 6000', 'Min DI 100', 'SFS guidelines', 'DLA/PIP offset'],
        'Income': ['Wage slip', 'Tax code', 'Benefit letters', 'UC journal', 'Self-employed', 'Newly self-employed', 'CIS invoice'],
        'Bank': ['Bank stmt 3m', 'Clear ownership', 'Gambling', 'GAMSTOP', 'DDs/SOs'],
        'Proof': ['Proof debts', 'Verbal', 'Credit report', 'Creditor letters', 'Debt collector', '3-way calls', 'CCJs', '3rd party', 'Duration'],
        'Previous IVA': ['IVA termination'],
        'HMRC': ['No deduction', 'Reject prev IVA', 'Reject bankruptcy', 'Late submission', 'Equity check', 'Bankruptcy return', 'Full & final', 'SEISS fraud', 'Joint debts', 'Min 4000', 'Benefits only'],
        'Watch': ['Equity exceeds', 'Council deduction', 'Recent spend'],
        'Creditor': ['Shop Direct 3/4m', 'Shop Direct 6m', 'Creation 4m', 'Link Mid SFS', 'Link 12000', 'Link equity', 'Link benefits', 'Link IVA']
    },
    'WATCH': {
        'Rejection': ['Debt <6y', 'Bankruptcy div', 'Equity>debt', 'Single creditor', 'Recent spending', 'Children >13', 'Age 80+', 'Antecedent', 'Car finance'],
        'Modification': ['Car value >9000', 'Car HP >400'],
        'Additional': ['Gambling', 'Previously proposed']
    },
    'TIX': {
        'Rejection': ['Shop Direct 3m', 'Shop Direct 6m', 'Creation 4m'],
        'Modification': ['Car HP >250'],
        'Update': ['Creditor update']
    },
    'EVOLVE': {
        'Rejection': ['Equity 100% LTV', 'Equity 85% LTV', 'Single creditor'],
        'Notes': ['Case 344167']
    }
}

# Get database rules
db_rules = {}
for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    rules = GlobalCriteria.objects.filter(criteria_set=criteria_set).order_by('rule_key')
    db_rules[criteria_set] = list(rules)

print("\n" + "="*130)
print("MISSING RULES ANALYSIS - DETAILED BREAKDOWN")
print("="*130)

for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    md_items = markdown_docs[criteria_set]
    db_rule_list = db_rules[criteria_set]
    
    # Count
    md_total = sum(len(v) for v in md_items.values())
    db_total = len(db_rule_list)
    missing = md_total - db_total
    
    # Get rule names
    db_names = set()
    for rule in db_rule_list:
        db_names.add(rule.rule_key.lower())
        db_names.add(rule.rule_name.lower())
    
    print(f"\n{'='*130}")
    print(f"{criteria_set.upper()} - Documented: {md_total} | Database: {db_total} | Missing: {missing}")
    print(f"{'='*130}")
    
    # Show by category
    for category, items in md_items.items():
        print(f"\n{category}:")
        for item in items:
            # Check if in database
            found = False
            for rule in db_rule_list:
                if item.lower() in rule.rule_key.lower() or item.lower() in rule.rule_name.lower():
                    status = "[A]" if rule.is_active else "[I]"
                    print(f"  [+] {item:25} -> {rule.rule_key:20} {status}")
                    found = True
                    break
            if not found:
                print(f"  [-] {item:25} -> MISSING IN DATABASE")

print("\n" + "="*130)
print("SUMMARY TABLE")
print("="*130)

summary_data = []
for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    md_items = markdown_docs[criteria_set]
    db_rule_list = db_rules[criteria_set]
    
    md_total = sum(len(v) for v in md_items.values())
    db_total = len(db_rule_list)
    active = sum(1 for r in db_rule_list if r.is_active)
    inactive = sum(1 for r in db_rule_list if not r.is_active)
    missing = md_total - db_total
    
    summary_data.append((criteria_set, md_total, db_total, active, inactive, missing))

print(f"\n{'Criteria':<10} | {'Markdown':<12} | {'DB Total':<10} | {'Active':<8} | {'Inactive':<10} | {'Missing':<10}")
print("-" * 130)
for cs, md, db, act, ina, miss in summary_data:
    print(f"{cs:<10} | {md:<12} | {db:<10} | {act:<8} | {ina:<10} | {miss:<10}")

total_md = sum(s[1] for s in summary_data)
total_db = sum(s[2] for s in summary_data)
total_active = sum(s[3] for s in summary_data)
total_inactive = sum(s[4] for s in summary_data)
total_missing = sum(s[5] for s in summary_data)

print("-" * 130)
print(f"{'TOTAL':<10} | {total_md:<12} | {total_db:<10} | {total_active:<8} | {total_inactive:<10} | {total_missing:<10}")

print("\n" + "="*130)
