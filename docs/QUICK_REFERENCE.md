# Django Debt Criteria - Quick Reference

## File Structure

```
debt_app/
├── __init__.py                          # App initialization
├── models.py                            # All model definitions
├── admin.py                             # Django admin config
├── apps.py                              # App config
├── helpers.py                           # Utility functions
├── serializers.py                       # DRF serializers (optional)
├── migrations/
│   ├── __init__.py
│   ├── 0001_initial.py                  # Create base models
│   └── 0002_extend_criteria_models.py   # Add new fields + CriteriaDecision
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       └── seed_criteria_rules.py       # Initialize GlobalCriteria rules
└── fixtures/
    └── global_criteria_seed.json        # Initial rule data

README.md                                 # Full documentation
MIGRATION_GUIDE.md                        # Integration instructions
EXAMPLES.md                               # Real-world usage examples
QUICK_REFERENCE.md                        # This file
```

## Installation (Quick)

```bash
# 1. Copy app to project
cp -r debt_app /path/to/project/

# 2. Add to settings.py
INSTALLED_APPS = ['debt_app.apps.DebtAppConfig']

# 3. Run migrations
python manage.py migrate debt_app

# 4. Load initial rules
python manage.py seed_criteria_rules
```

## Models Overview

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| **CreditorCriteria** | Creditor info & rules | name, trading_names, representative, min_dividend_pence, parent_group, is_active |
| **GlobalCriteria** | Configurable rules | rule_key (unique), criteria_set, severity, threshold_value |
| **CriteriaDecision** | Audit log | application_id, recommendation, passes_all_hard_blocks, input/output_snapshot |
| **Application** | Case reference | aryza_reference, client_name |
| **EvidenceLedger** | Evidence log | application, entry_type |
| **Voter** | System user | name |

## Key Features

### ✓ Configurable Rules (No Code Changes)
```python
# Get majority threshold
rule = GlobalCriteria.objects.get(rule_key='majority_threshold')
print(rule.threshold_value)  # 75.00

# Update it
rule.threshold_value = 80.00
rule.save()  # Works immediately everywhere
```

### ✓ Audit Trail
Every decision logged in CriteriaDecision with:
- Full input/output snapshots (JSONField)
- Who made the decision (triggered_by)
- When (triggered_at with index)
- Source (STANDALONE or CASE_ASSESSMENT)

### ✓ Parent Group Banking Conflicts
```python
# Check if client's bank account is in same group as creditors
conflict = check_parent_group_conflict(
    client_bank='Lloyds',
    debtor_creditors=['MBNA', 'Scottish Widows']
)
# Returns: True (all in Lloyds Banking Group)
```

### ✓ Trading Names Support
```python
creditor = CreditorCriteria.objects.create(
    name='Shop Direct Group',
    trading_names=['Very', 'Littlewoods', 'Littlewoods.com']
)
```

### ✓ Database Indexes
- CreditorCriteria: name, representative, is_active  
- GlobalCriteria: rule_key, criteria_set
- CriteriaDecision: application_id, triggered_at

## Common Tasks

### Find a creditor
```python
from debt_app.models import CreditorCriteria

# By name
creditor = CreditorCriteria.objects.get(name='Lloyds')

# All active
creditors = CreditorCriteria.objects.filter(is_active=True)

# Watch-listed
watch = CreditorCriteria.objects.filter(is_watch=True)
```

### Get a rule
```python
from debt_app.models import GlobalCriteria

# By key
rule = GlobalCriteria.objects.get(rule_key='majority_threshold')

# All for a criteria set
tig_rules = GlobalCriteria.objects.filter(criteria_set='TIG')

# All hard blocks
hard = GlobalCriteria.objects.filter(severity='hard_block')
```

### Log a decision
```python
from debt_app.models import CriteriaDecision

decision = CriteriaDecision.objects.create(
    application_id='ARY-2026-45821',
    client_name='John Smith',
    input_snapshot={'debt': 15000},
    decision_output={'recommendation': 'IVA'},
    recommended_solution='IVA',
    passes_all_hard_blocks=True,
    triggered_by=user,
    source='CASE_ASSESSMENT'
)
```

### Get decisions for an application
```python
from debt_app.helpers import get_criteria_decisions_for_application

decisions = get_criteria_decisions_for_application('ARY-2026-45821')
for d in decisions:
    print(f"{d.triggered_at}: {d.recommended_solution}")
```

## Helper Functions (debt_app/helpers.py)

| Function | Purpose | Returns |
|----------|---------|---------|
| `get_rule_threshold(rule_key)` | Get numeric threshold | Decimal |
| `get_majority_threshold()` | Get 75% default | Decimal |
| `log_criteria_decision(...)` | Record decision | CriteriaDecision |
| `get_creditor_by_trading_name(name)` | Find by trading name | CreditorCriteria |
| `check_parent_group_conflict(...)` | Check banking group | Boolean |
| `get_criteria_decisions_for_application(id)` | Get case decisions | QuerySet |

## Representatives (Enum)
- `'WATCH'` - Watch representative
- `'TIX'` - TIX representative  
- `'EVOLVE'` - Evolve representative
- `'NONE'` - No representative (default)

## Criteria Sets (Enum)
- `'TIG'` - TIG scheme
- `'WATCH'` - Watch scheme
- `'TIX'` - TIX scheme
- `'EVOLVE'` - Evolve scheme

## Severity Levels (Enum)
- `'hard_block'` - Absolutely must pass or application blocked
- `'flag'` - Issue for review but not blocking
- `'info'` - Informational only

## Recommended Solutions (Enum)
- `'IVA'` - Individual Voluntary Arrangement
- `'DMP'` - Debt Management Plan
- `'FREE_SECTOR'` - Free sector solution
- `'UNCLEAR'` - Decision unclear, needs review

## Sources (Enum)
- `'STANDALONE'` - Standalone criteria assessment
- `'CASE_ASSESSMENT'` - Part of case assessment

## Troubleshooting

**Migration failed**: See MIGRATION_GUIDE.md section "Troubleshooting"

**ArrayField error**: Use JSONField instead (see MIGRATION_GUIDE.md)

**No User access**: Ensure django.contrib.auth is in INSTALLED_APPS before debt_app

**Indexes missing**: Re-run `python manage.py migrate`

## Admin Interface

Access Django admin at `/admin/`:
- Manage CreditorCriteria & GlobalCriteria
- View CriteriaDecision audit log (read-only)
- Filter and search all models

## Performance Tips

1. Use indexes for filters
   ```python
   # Fast (indexed)
   CreditorCriteria.objects.filter(is_active=True)
   
   # Slow (not indexed)
   CreditorCriteria.objects.filter(contact_email__isnull=False)
   ```

2. Use select_related for ForeignKey
   ```python
   decisions = CriteriaDecision.objects.select_related('triggered_by')
   ```

3. Cache threshold values
   ```python
   MAJORITY_THRESHOLD = Decimal('75.00')  # Cache after load
   ```

## Documentation Files

- **README.md** - Full feature documentation
- **MIGRATION_GUIDE.md** - How to integrate into existing project
- **EXAMPLES.md** - Real-world usage patterns  
- **QUICK_REFERENCE.md** - This file

## Django Settings Required

```python
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.postgres',  # For ArrayField
    'debt_app.apps.DebtAppConfig',
]
```

## Next: Run Examples

See EXAMPLES.md for complete code samples of:
- Creating creditors
- Updating thresholds
- Logging decisions
- Building audit trails
- Full assessment workflows
