import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from debt_app.models import GlobalCriteria
import debt_app.criteria_engine as ce

basic_rules = ce.basic_rules
docs_rules = ce.docs_rules
creditor_rules = ce.creditor_rules
docs_creditor_rules = ce.docs_creditor_rules

watch_basic_rules = [
    ce._rule_watch_debt_repayable_under_6_years,
    ce._rule_watch_bankruptcy_higher,
    ce._rule_watch_equity_exceeds_debt,
    ce._rule_watch_single_creditor,
    ce._rule_watch_antecedent_transactions,
    ce._rule_watch_client_age_80,
    ce._rule_watch_vehicle_over_9000,
]

watch_docs_rules = [
    ce._rule_watch_recent_car_finance,
    ce._rule_watch_vulnerability_no_evidence,
    ce._rule_watch_children_over_13,
    ce._rule_watch_hp_over_400,
    ce._rule_watch_gambling_no_clean_statements,
    ce._rule_watch_previous_proposal,
]

watch_creditor_rules = [
    ce._rule_watch_recent_spending,
]

all_rules = basic_rules + docs_rules + creditor_rules + docs_creditor_rules + watch_basic_rules + watch_docs_rules + watch_creditor_rules

for rule_func in all_rules:
    rule_key = rule_func.__name__.replace('_rule_', '')
    rule_name = rule_key.replace('_', ' ').title()
    
    # Defaults for thresholds
    threshold = None
    if rule_key == 'min_debt':
        threshold = 500000 # 5000 pounds
    elif rule_key == 'min_di':
        threshold = 5000 # 50 pounds
        
    criteria_set = 'WATCH' if rule_key.startswith('watch') else 'TIG'
    
    GlobalCriteria.objects.update_or_create(
        rule_key=rule_key,
        defaults={
            'rule_name': rule_name,
            'is_active': True,
            'criteria_set': criteria_set,
            'severity': 'hard_block',
            'threshold_value': threshold
        }
    )

print("All rules seeded and activated successfully!")
