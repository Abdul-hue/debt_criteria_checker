#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.models import GlobalCriteria

# Get all database rules with full details
db_by_set = {}
for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    rules = GlobalCriteria.objects.filter(criteria_set=criteria_set).order_by('rule_key')
    db_by_set[criteria_set] = {
        'total': rules.count(),
        'active': rules.filter(is_active=True).count(),
        'inactive': rules.filter(is_active=False).count(),
        'rules': [(r.rule_key, r.rule_name, r.severity, r.is_active) for r in rules]
    }

# Actual markdown items (from the files)
markdown_actual = {
    'TIG': {
        'Core Requirements': [
            'Minimum Debt Level (6000)',
            'Minimum Disposable Income (100)',
            'Financial Statement (SFS guidelines)',
            'DLA/PIP offset'
        ],
        'Income Requirements': [
            '1 full month wage slip (last 3 months)',
            'Tax Code verification',
            'Benefit letters (current financial year)',
            'Universal Credit journal (last 3 months)',
            'Self-employed income (Tax Return / 3 months banking)',
            'Newly self-employed (minimum 3 months)',
            'CIS invoice (1 month with 20% deduction)'
        ],
        'Bank Statements': [
            'Bank statement (last 3 months)',
            'Clear account ownership',
            'Gambling limit (under 1000)',
            'GAMSTOP requirement (if over 200)',
            'DDs/SOs explanation required'
        ],
        'Proof of Debts': [
            'Proof of all debts required',
            'Verbal allowed for debts under 1000',
            'Credit Report (Shop Direct granular)',
            'Creditor Letters (dated within 6 weeks)',
            'Debt Collector Letters (with original creditor)',
            '3-Way Calls (with time marker)',
            'CCJs (original creditor details)',
            '3rd Party Letters (signed/dated/address)',
            'Third-party contributions (duration stated)'
        ],
        'Previous IVA': [
            'Termination report required'
        ],
        'HMRC Rules': [
            'HMRC no income/benefit deduction',
            'HMRC reject if previous IVA/Bankruptcy',
            'HMRC Self Assessment late submissions',
            'HMRC equity check',
            'HMRC bankruptcy return comparison',
            'HMRC full & final savings origin check',
            'SEISS fraud (cannot be included)',
            'Joint debts (name removal)',
            'Minimum debt threshold (4000)',
            'Benefits-only rejection'
        ],
        'General Flags': [
            'Equity exceeds liabilities',
            'Council majority deductions',
            'Recent spend monitoring'
        ],
        'Creditor-Specific': [
            'Shop Direct (3/4 month rule)',
            'Shop Direct (6 month account age)',
            'Creation/Sygma/Laser (4 month rule)',
            'Link Financial (Mid SFS only)',
            'Link Financial (12000 minimum)',
            'Link Financial (equity check)',
            'Link Financial (benefits 10% max)',
            'Link Financial (previous IVA arrears)'
        ]
    },
    'WATCH': {
        'Rejection Rules': [
            'Debt repayable within 6 years',
            'Bankruptcy dividend higher than IVA',
            'Equity greater than debt',
            'Single creditor only',
            'Recent spending within 3 months',
            'Children over 13 without sustainability',
            'Client aged 80 or above',
            'Antecedent transactions appear',
            'Car finance taken in last 3 months'
        ],
        'Modification Rules': [
            'Car value >9000 - downgrade to 4500',
            'Car HP >400 per month'
        ],
        'Additional': [
            'Gambling as main cause',
            'Previously proposed IVA'
        ]
    },
    'TIX': {
        'Rejection Rules': [
            'Shop Direct recent spend (3 months)',
            'Shop Direct account less than 6 months',
            'Creation/Sygma/Laser recent spend (4 months)'
        ],
        'Modification Rules': [
            'Car HP >250 per month'
        ],
        'Updates': [
            'Creditor representation (UKAR, Whistletree, etc.)'
        ]
    },
    'EVOLVE': {
        'Rejection Rules': [
            'Equity higher than debt (100% LTV)',
            'Equity higher than debt (85% LTV)',
            'Single creditor with <500 other'
        ],
        'Reference': [
            'Case 344167 - Caroline Williams (trial)'
        ]
    }
}

# Print detailed report
print("\n" + "="*140)
print("MISSING RULES - DETAILED ANALYSIS TABLE")
print("="*140)

all_missing = []

for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    db_info = db_by_set[criteria_set]
    md_categories = markdown_actual[criteria_set]
    
    print(f"\n{'='*140}")
    print(f"{criteria_set.upper()}")
    print(f"{'='*140}")
    
    print(f"Database Rules: Total={db_info['total']} | Active={db_info['active']} | Inactive={db_info['inactive']}")
    print(f"\nDatabase Rules in System:")
    for rule_key, rule_name, severity, is_active in db_info['rules']:
        status = "ACTIVE" if is_active else "INACTIVE"
        print(f"  {rule_key:25} | {rule_name:40} | {severity:12} | {status}")
    
    # Count markdown items
    md_total = sum(len(items) for items in md_categories.values())
    missing_in_md = []
    
    print(f"\n{'-'*140}")
    print(f"Markdown Documentation: {md_total} items")
    print(f"{'-'*140}")
    
    for category, items in md_categories.items():
        print(f"\n{category}:")
        for item in items:
            # Try to find in database
            found = False
            for rule_key, rule_name, severity, is_active in db_info['rules']:
                # Simple keyword matching
                keywords_in_item = item.lower().split()
                keywords_in_rule = (rule_key + ' ' + rule_name).lower()
                
                if any(kw in keywords_in_rule for kw in keywords_in_item if len(kw) > 3):
                    status = "ACTIVE" if is_active else "INACTIVE"
                    print(f"  [+] {item:50} -> {rule_key:25} [{status}]")
                    found = True
                    break
            
            if not found:
                print(f"  [-] {item:50} -> NOT IN DATABASE *** MISSING ***")
                all_missing.append({
                    'criteria': criteria_set,
                    'category': category,
                    'item': item
                })

print("\n\n" + "="*140)
print("SUMMARY - TOTAL MISSING RULES BY CRITERIA SET")
print("="*140)

summary = {}
for criteria_set in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    db_info = db_by_set[criteria_set]
    md_categories = markdown_actual[criteria_set]
    md_total = sum(len(items) for items in md_categories.values())
    
    missing = len([m for m in all_missing if m['criteria'] == criteria_set])
    
    summary[criteria_set] = {
        'markdown': md_total,
        'database': db_info['total'],
        'active': db_info['active'],
        'inactive': db_info['inactive'],
        'missing': missing
    }

print(f"\n{'Criteria':<12} | {'Markdown':<12} | {'Database':<12} | {'Active':<10} | {'Inactive':<10} | {'Missing':<12} | {'Coverage %'}")
print("-" * 140)

for cs in ['TIG', 'WATCH', 'TIX', 'EVOLVE']:
    s = summary[cs]
    coverage = (s['database'] / s['markdown'] * 100) if s['markdown'] > 0 else 0
    print(f"{cs:<12} | {s['markdown']:<12} | {s['database']:<12} | {s['active']:<10} | {s['inactive']:<10} | {s['missing']:<12} | {coverage:>6.1f}%")

total_md = sum(s['markdown'] for s in summary.values())
total_db = sum(s['database'] for s in summary.values())
total_active = sum(s['active'] for s in summary.values())
total_inactive = sum(s['inactive'] for s in summary.values())
total_missing = len(all_missing)
total_coverage = (total_db / total_md * 100) if total_md > 0 else 0

print("-" * 140)
print(f"{'TOTAL':<12} | {total_md:<12} | {total_db:<12} | {total_active:<10} | {total_inactive:<10} | {total_missing:<12} | {total_coverage:>6.1f}%")

print("\n" + "="*140)
print(f"CONCLUSION: {total_missing} RULES MISSING FROM DATABASE (Out of {total_md} documented)")
print("="*140)
