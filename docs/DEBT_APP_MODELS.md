# debt_app models reference

> Historical notes on the criteria models, their fields and the audit trail.
> For how to run the project, see the top-level `README.md`.

This extension adds comprehensive criteria management capabilities to your Django debt application. It includes new fields for creditor and global criteria, a new audit logging model, and database indexing for performance.

## What's Included

### Updated Models

#### CreditorCriteria
New fields added:
- **trading_names** (ArrayField): Alternative names the creditor may appear under
- **representative** (CharField): Creditor representative (WATCH, TIX, EVOLVE, NONE)
- **min_dividend_pence** (IntegerField): Minimum pence per pound threshold
- **contact_email** (EmailField): Creditor contact email
- **contact_phone** (CharField): Creditor phone number
- **is_active** (BooleanField): Activation flag
- **is_watch**, **is_tix**, **is_evolve** (BooleanField): Criteria classification flags
- **parent_group** (CharField): Banking group association (for conflict of interest checking)
- **updated_by** (ForeignKey): Tracks which user last modified the record
- **last_updated** (DateTimeField): Automatic timestamp update on changes

**Indexes:**
- name
- representative
- is_active

#### GlobalCriteria
New fields added:
- **criteria_set** (CharField): Classification set (TIG, WATCH, TIX, EVOLVE)
- **rule_key** (CharField): Unique rule identifier (e.g., "majority_threshold", "min_debt")
- **rule_name** (CharField): Human-readable rule name
- **severity** (CharField): Hard block / Flag / Info level
- **is_active** (BooleanField): Rule activation flag
- **threshold_value** (DecimalField): Numeric threshold for the rule
- **updated_by** (ForeignKey): Audit trail for modifications
- **last_updated** (DateTimeField): Automatic timestamp

**Indexes:**
- rule_key
- criteria_set

### New Model: CriteriaDecision

Complete audit log for all criteria decisions:
- **id** (UUIDField): Primary key
- **application_id** (CharField): Aryza reference number
- **client_name** (CharField): Client name
- **input_snapshot** (JSONField): Full input data sent to engine
- **decision_output** (JSONField): Full output from engine
- **recommended_solution** (CharField): IVA, DMP, FREE_SECTOR, or UNCLEAR
- **passes_all_hard_blocks** (BooleanField): Compliance flag
- **triggered_by** (ForeignKey): User who triggered the decision
- **triggered_at** (DateTimeField): Auto-recorded timestamp
- **source** (CharField): STANDALONE or CASE_ASSESSMENT

**Indexes:**
- application_id
- triggered_at

## Installation Steps

### 1. Copy the app to your project

```bash
cp -r debt_app /path/to/your/project/
```

### 2. Add to INSTALLED_APPS

In your `settings.py`:

```python
INSTALLED_APPS = [
    # ... other apps
    'debt_app.apps.DebtAppConfig',
]
```

### 3. Run migrations

```bash
python manage.py migrate debt_app
```

This will run:
- `0001_initial.py` - Creates base models
- `0002_extend_criteria_models.py` - Adds new fields and CriteriaDecision model

### 4. Load initial GlobalCriteria rules (Optional)

To set up the configurable majority threshold and other default rules:

```bash
python manage.py loaddata debt_app/fixtures/global_criteria_seed.json
```

Or use the Django shell:

```python
from debt_app.models import GlobalCriteria

# Majority Creditor Threshold (75%)
GlobalCriteria.objects.create(
    criteria_set='TIG',
    rule_key='majority_threshold',
    rule_name='Majority Creditor Threshold',
    severity='hard_block',
    threshold_value=75.00
)
```

## Key Features

### Majority Threshold Configuration
The 75% majority creditor threshold is now configurable via database:
```python
majority_rule = GlobalCriteria.objects.get(rule_key='majority_threshold')
threshold = majority_rule.threshold_value  # 75.00
```

This allows updates without code changes.

### Audit Trail
Every criteria decision is logged in `CriteriaDecision` with:
- Full input and output snapshots
- User who triggered the assessment
- Exact timestamp
- Source (standalone or case assessment)

### Parent Group Banking
The `parent_group` field on CreditorCriteria enables checking for conflicts:
- Clients cannot have current accounts with banks where they have debt
- Example: Lloyds Banking Group includes Lloyds, Scottish Widows, MBNA

### CSV Import/Export
Example import script for bulk creditor updates:

```python
import csv
from debt_app.models import CreditorCriteria

with open('creditors.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        creditor, created = CreditorCriteria.objects.get_or_create(
            name=row['name'],
            defaults={
                'representative': row.get('representative', 'NONE'),
                'min_dividend_pence': row.get('min_dividend_pence'),
                'parent_group': row.get('parent_group'),
                'is_active': row.get('is_active', 'true').lower() == 'true',
            }
        )
```

## Migration Safety

Both migrations use safe practices:
- All new fields have sensible defaults
- ForeignKeys use `SET_NULL` to prevent cascade deletes
- UUID primary key on CriteriaDecision ensures globally unique IDs
- No existing data is modified or deleted

## Database Performance

### Indexes Added

**CreditorCriteria:**
```
- name: Fast lookups by creditor name
- representative: Filter by creditor representative
- is_active: Quick filtering of active/inactive creditors
```

**GlobalCriteria:**
```
- rule_key: O(1) lookups for specific rules
- criteria_set: Fast filtering by criteria set (TIG, WATCH, etc.)
```

**CriteriaDecision:**
```
- application_id: Retrieve all decisions for an application
- triggered_at: Time-based queries and sorting
```

## Django Admin Integration

Full Django admin support is included in `admin.py`:
- View and manage creditor criteria
- Edit global rules and thresholds
- View decision audit log (read-only for integrity)
- Filtering and search across all models

## Usage Examples

### Query majority threshold
```python
from debt_app.models import GlobalCriteria

threshold = GlobalCriteria.objects.get(
    rule_key='majority_threshold'
).threshold_value
# Returns Decimal('75.00')
```

### Log a criteria decision
```python
from debt_app.models import CriteriaDecision
from django.contrib.auth.models import User

user = User.objects.get(username='assessor_user')
decision = CriteriaDecision.objects.create(
    application_id='ARY-2026-12345',
    client_name='John Smith',
    input_snapshot={'debt': 15000, 'income': 2000},
    decision_output={'recommendation': 'IVA', 'reasons': ['High debt ratio']},
    recommended_solution='IVA',
    passes_all_hard_blocks=True,
    triggered_by=user,
    source='CASE_ASSESSMENT'
)
```

### Filter decisions
```python
# Get all decisions for an application
from debt_app.models import CriteriaDecision

decisions = CriteriaDecision.objects.filter(
    application_id='ARY-2026-12345'
).order_by('-triggered_at')

# Get decisions from last 7 days
from datetime import timedelta
from django.utils import timezone

recent = CriteriaDecision.objects.filter(
    triggered_at__gte=timezone.now() - timedelta(days=7)
)
```

## Troubleshooting

### Migration Conflicts
If you have existing migrations after `0001_initial`, ensure `0002_extend_criteria_models.py` has the correct dependency in the `dependencies` list.

### ArrayField Issues (PostgreSQL only)
If using PostgreSQL, ensure `django.contrib.postgres` is installed:
```bash
pip install psycopg2-binary
```

For other databases, convert `trading_names` to a separate related model or use JSONField.

### Foreign Key to User
Ensure `django.contrib.auth` is in INSTALLED_APPS.

## Support

For issues or questions about this extension, refer to:
- `models.py` for detailed field definitions
- `admin.py` for customization examples
- `migrations/` for migration structure
