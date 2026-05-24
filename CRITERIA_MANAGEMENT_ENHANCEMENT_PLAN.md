# CRITERIA MANAGEMENT SYSTEM - COMPREHENSIVE IMPLEMENTATION PLAN

**Date:** May 22, 2026  
**Status:** Current System Analysis + Enhancement Plan  
**Objective:** Enhance database schema and frontend UI to fully manage all 58 criteria rules with complete documentation

---

## CURRENT STATE VERIFICATION

### ✅ Already Implemented

| Component | Status | Location |
|-----------|--------|----------|
| **Database Model** | ✅ Complete | `debt_app/models.py` - `GlobalCriteria` |
| **API Endpoints** | ✅ Complete | `debt_app/views/criteria_views.py` - `RulesListView`, `RulesDetailView` |
| **URL Routing** | ✅ Complete | `debt_app/urls_criteria.py` - `/api/rules/`, `/api/rules/<str:rule_key>/` |
| **Frontend UI** | ✅ Complete | `frontend/src/pages/RulesPage.jsx` + `components/rules/RulesList.jsx` |
| **Admin Panel** | ✅ Complete | Django admin interface for GlobalCriteria |

### ✅ Test: TIG-20.1 Verification
```
Rule Key: TIG-20.1
Name: Creation Sygma Laser hard block
Criteria Set: TIG
Severity: hard_block
Active: True
Threshold Value: None
```
**Status:** CONFIRMED IN DATABASE ✅

---

## DATABASE SCHEMA ENHANCEMENT

### Current `GlobalCriteria` Model Fields

```python
class GlobalCriteria(models.Model):
    # Identification
    id = BigAutoField (primary key)
    rule_key = CharField (unique)           # e.g., "TIG-20.1"
    rule_name = CharField                   # e.g., "Creation Sygma Laser hard block"
    
    # Classification
    criteria_set = CharField (choices)      # TIG, WATCH, TIX, EVOLVE
    severity = CharField (choices)          # hard_block, flag, info
    is_active = BooleanField (default True)
    
    # Values
    threshold_value = DecimalField (nullable) # e.g., 6000 for min debt
    
    # Audit
    updated_by = ForeignKey(User)
    last_updated = DateTimeField (auto_now)
```

### Recommended Enhanced Schema (NEW FIELDS)

Add these fields to `GlobalCriteria` to store comprehensive documentation:

```python
# Documentation & Context Fields
description = TextField(
    blank=True, 
    null=True,
    help_text="Full description of what this rule validates"
)

implementation_notes = TextField(
    blank=True,
    null=True,
    help_text="Technical implementation details and edge cases"
)

category = CharField(
    max_length=100,
    blank=True,
    choices=[
        ('income', 'Income Requirements'),
        ('bank_statements', 'Bank Statements'),
        ('proof_of_debts', 'Proof of Debts'),
        ('creditor_specific', 'Creditor-Specific'),
        ('hmrc', 'HMRC'),
        ('vehicle', 'Vehicle/Transportation'),
        ('spending', 'Spending Patterns'),
        ('council', 'Council Rules'),
        ('other', 'Other'),
    ],
    help_text="Rule category for organization"
)

example_case = TextField(
    blank=True,
    null=True,
    help_text="Example case scenario where this rule applies"
)

rejection_message = TextField(
    blank=True,
    null=True,
    help_text="User-facing message if rule fails (hard_block)"
)

flag_message = TextField(
    blank=True,
    null=True,
    help_text="User-facing message for flag rules"
)

# Metadata
is_creditor_specific = BooleanField(
    default=False,
    help_text="If True, this rule applies per-creditor"
)

applies_to_creditors = JSONField(
    default=list,
    blank=True,
    help_text="List of creditors this rule specifically applies to (e.g., ['Shop Direct', 'Creation'])"
)

references = JSONField(
    default=list,
    blank=True,
    help_text="References to markdown docs, Excel sheets, or external sources"
)

# Derived/Calculated Fields
execution_order = IntegerField(
    default=0,
    help_text="Order in which rule should be evaluated"
)

depends_on_rules = JSONField(
    default=list,
    blank=True,
    help_text="Rule keys that must be evaluated before this one"
)

related_rules = JSONField(
    default=list,
    blank=True,
    help_text="Related rule keys (similar logic or related validation)"
)

last_reviewed = DateField(
    blank=True,
    null=True,
    help_text="Last date this rule was reviewed for accuracy"
)

review_notes = TextField(
    blank=True,
    null=True,
    help_text="Notes from last review"
)
```

### Migration Path

```sql
-- Create new fields as nullable initially
ALTER TABLE debt_app_globalcriteria ADD COLUMN description TEXT NULL;
ALTER TABLE debt_app_globalcriteria ADD COLUMN implementation_notes TEXT NULL;
ALTER TABLE debt_app_globalcriteria ADD COLUMN category VARCHAR(100) NULL;
... (etc for each field)

-- Populate from markdown data
UPDATE debt_app_globalcriteria 
SET description = '...' 
WHERE rule_key IN ('TIG-01', 'TIG-02', ...);

-- Remove NULL constraint once populated
ALTER TABLE debt_app_globalcriteria MODIFY description TEXT NOT NULL;
```

---

## FRONTEND UI ENHANCEMENT PLAN

### Current State: RulesList Component

**File:** `frontend/src/components/rules/RulesList.jsx`

**Current Features:**
- ✅ Display all 58 rules in filterable table
- ✅ Filter by criteria set (TIG/WATCH/TIX/EVOLVE)
- ✅ Filter by severity (hard_block/flag/info)
- ✅ Search by rule_key or name
- ✅ Edit inline (activate/deactivate)
- ✅ Delete rules
- ✅ Color-coded badges

**Missing Features:**
- ❌ Display category
- ❌ Show description/notes
- ❌ Display threshold values with units
- ❌ Show creditor-specific info
- ❌ Display related rules
- ❌ Show review dates
- ❌ Documentation links

### Enhanced UI Component Structure

```
RulesPage (parent)
├── Tabs: Creditors | Global Rules | Councils
│
└── RulesList (enhanced)
    ├── Statistics Bar
    │   ├── Total: 58 rules
    │   ├── By criteria set (TIG: 35, WATCH: 14, TIX: 6, EVOLVE: 3)
    │   ├── By severity (Hard Block: 38, Flag: 16, Info: 4)
    │   └── By category (Income: 7, Bank: 5, etc.)
    │
    ├── Search & Filter Bar
    │   ├── Search input (rule_key, name, description)
    │   ├── Criteria set filter (TIG/WATCH/TIX/EVOLVE)
    │   ├── Severity filter (hard_block/flag/info)
    │   ├── Category filter (NEW)
    │   ├── Active/Inactive toggle
    │   └── Clear filters button
    │
    ├── Rules Table
    │   ├── Columns:
    │   │   ├── Rule Key (TIG-01, etc.)
    │   │   ├── Name
    │   │   ├── Category (NEW) - Icon + label
    │   │   ├── Criteria Set - Color badge
    │   │   ├── Severity - Color badge
    │   │   ├── Threshold Value (NEW) - Display with units
    │   │   ├── Active - Toggle switch
    │   │   ├── Last Reviewed (NEW) - Date or "Pending"
    │   │   └── Actions - Edit, View, Delete
    │   │
    │   └── Row Interactions:
    │       ├── Click row → RuleDetailDrawer (read-only initially)
    │       ├── Edit button → RuleEditDrawer (full edit)
    │       └── Delete button → ConfirmDialog
    │
    ├── RuleDetailDrawer (NEW - Read-only)
    │   ├── Rule information (key, name, criteria set, severity)
    │   ├── Description & purpose
    │   ├── Implementation notes
    │   ├── Example case scenario
    │   ├── Threshold value with context
    │   ├── Messages (rejection, flag)
    │   ├── Creditor-specific info
    │   ├── Related rules (clickable links)
    │   ├── References & source docs
    │   ├── Review history
    │   └── Edit button → switch to RuleEditDrawer
    │
    └── RuleEditDrawer (existing - ENHANCED)
        ├── All read-only fields from detail view
        ├── Editable fields:
        │   ├── Rule name
        │   ├── Description
        │   ├── Implementation notes
        │   ├── Category (dropdown)
        │   ├── Severity (dropdown)
        │   ├── Threshold value
        │   ├── Rejection message
        │   ├── Flag message
        │   ├── Is active (toggle)
        │   ├── Creditor-specific (toggle + multi-select)
        │   ├── Related rules (multi-select searchable)
        │   ├── Review date
        │   └── Review notes
        │
        ├── Validation:
        │   ├── Rule key is immutable
        │   ├── Criteria set is immutable
        │   ├── Threshold value must be numeric
        │   └── Required fields check
        │
        └── Actions:
            ├── Save (PATCH to /api/rules/<rule_key>/)
            ├── Cancel
            └── Delete (moved to detail view)
```

### Component Files to Create/Modify

**New Components:**
1. `frontend/src/components/rules/RuleDetailDrawer.jsx` (NEW)
   - Read-only display of complete rule information
   - Shows all fields including documentation
   - Links to related rules
   - Displays references

2. `frontend/src/hooks/useRuleDetail.js` (NEW)
   - Fetch single rule with all fields
   - Cache rule details

**Modified Components:**
1. `frontend/src/components/rules/RuleEditDrawer.jsx` (ENHANCED)
   - Add all new fields
   - Enhanced form validation
   - Better UX for complex fields (related_rules, references)

2. `frontend/src/components/rules/RulesList.jsx` (ENHANCED)
   - Add category filter
   - Show category column
   - Threshold value display with units
   - Review date display
   - Click to detail view

---

## API ENDPOINT SPECIFICATIONS

### Current Endpoints

#### GET `/api/rules/`
**Returns:** Paginated list of rules

**Response:**
```json
{
  "count": 58,
  "results": [
    {
      "id": 1,
      "rule_key": "TIG-01",
      "name": "Minimum debt",
      "criteria_set": "TIG",
      "severity": "hard_block",
      "is_active": true,
      "threshold_value": 6000.0,
      "last_updated": "2026-05-22T10:30:00Z"
    }
  ]
}
```

#### GET `/api/rules/<str:rule_key>/`
**Returns:** Single rule details

#### PUT `/api/rules/<str:rule_key>/`
**Updates:** Rule fields

#### DELETE `/api/rules/<str:rule_key>/`
**Deletes:** Rule record

### Enhanced Endpoint Response (with new fields)

**GET `/api/rules/?include=full`** (NEW query parameter)

```json
{
  "count": 58,
  "results": [
    {
      "id": 1,
      "rule_key": "TIG-01",
      "name": "Minimum debt",
      "criteria_set": "TIG",
      "severity": "hard_block",
      "is_active": true,
      "threshold_value": 6000.0,
      "category": "income",
      "description": "All cases must have a minimum debt level of £6,000. This ensures...",
      "implementation_notes": "Check debt_app.models.Application.total_debt >= 6000",
      "example_case": "Client has debts totaling £5,500 with Natwest and HSBC. Rule FAILS.",
      "rejection_message": "Total debt is below minimum threshold of £6,000",
      "is_creditor_specific": false,
      "applies_to_creditors": [],
      "references": [
        "TIG_Criteria.md - Core Requirements",
        "debt_app/criteria_engine.py line 123"
      ],
      "execution_order": 1,
      "depends_on_rules": [],
      "related_rules": ["TIG-02"],
      "last_reviewed": "2026-05-01",
      "review_notes": "Verified against Excel Criteria sheet",
      "last_updated": "2026-05-22T10:30:00Z"
    }
  ]
}
```

### View Modifications

**File:** `debt_app/views/criteria_views.py`

```python
def _rule_obj_to_dict(rule, include_full=False):
    """Serialize GlobalCriteria to dict, optionally including all fields."""
    data = {
        "id": rule.id,
        "rule_key": rule.rule_key,
        "name": rule.rule_name,
        "criteria_set": rule.criteria_set,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "threshold_value": rule.threshold_value,
        "last_updated": rule.last_updated.isoformat(),
    }
    
    if include_full:
        data.update({
            "description": rule.description,
            "implementation_notes": rule.implementation_notes,
            "category": rule.category,
            "example_case": rule.example_case,
            "rejection_message": rule.rejection_message,
            "flag_message": rule.flag_message,
            "is_creditor_specific": rule.is_creditor_specific,
            "applies_to_creditors": rule.applies_to_creditors,
            "references": rule.references,
            "execution_order": rule.execution_order,
            "depends_on_rules": rule.depends_on_rules,
            "related_rules": rule.related_rules,
            "last_reviewed": rule.last_reviewed.isoformat() if rule.last_reviewed else None,
            "review_notes": rule.review_notes,
        })
    
    return data

class RulesListView(APIView):
    def get(self, request):
        include_full = request.query_params.get('include') == 'full'
        # ... existing code ...
        return Response({
            "count": paginator.count,
            "results": [_rule_obj_to_dict(r, include_full) for r in page_obj],
        })
```

---

## DATA POPULATION STRATEGY

### Phase 1: Populate Core Fields (Manual + Script)

**Priority Order:**
1. `description` - From markdown files (TIG_Criteria.md, etc.)
2. `category` - Auto-detect or manual for each rule
3. `rejection_message` - From criteria documentation
4. `threshold_value` - Already populated for some rules (6000, 100, 4000, etc.)

**Script:** `populate_rule_documentation.py`

```python
# Pseudo-code
rules_data = {
    'TIG-01': {
        'description': 'Minimum debt level for case eligibility',
        'category': 'income',
        'rejection_message': 'Total debt is below £6,000 minimum',
        'threshold_value': 6000
    },
    'TIG-20.1': {
        'description': 'Prevents acceptance of Creation/Sygma/Laser cards with recent spending',
        'category': 'creditor_specific',
        'applies_to_creditors': ['Creation', 'Sygma', 'Laser'],
        'rejection_message': 'Creation/Sygma/Laser recent activity detected'
    },
    # ... all 58 rules ...
}

for rule_key, data in rules_data.items():
    rule = GlobalCriteria.objects.get(rule_key=rule_key)
    for field, value in data.items():
        setattr(rule, field, value)
    rule.save()
```

### Phase 2: Create Related Rules Links

**Script:** `create_rule_relationships.py`

```python
# Link related rules
related_pairs = [
    ('TIG-01', 'TIG-02'),           # Min debt + Min DI
    ('TIG-19', 'TIG-19.1'),         # Shop Direct spend + account age
    ('WATCH-22.2', 'WATCH-22.4'),   # Debt repayable + equity check
]

for rule_key1, rule_key2 in related_pairs:
    r1 = GlobalCriteria.objects.get(rule_key=rule_key1)
    r2 = GlobalCriteria.objects.get(rule_key=rule_key2)
    
    r1.related_rules = list(set(r1.related_rules + [rule_key2]))
    r2.related_rules = list(set(r2.related_rules + [rule_key1]))
    
    r1.save()
    r2.save()
```

### Phase 3: Set Review Dates & Notes

**Manual Process:**
1. Review each rule's accuracy vs. markdown/Excel criteria
2. Set `last_reviewed` date
3. Add any `review_notes`
4. Update `is_active` status if needed

---

## IMPLEMENTATION TIMELINE

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **1. Schema Migration** | 1-2 days | Database migration, new model fields, data population script |
| **2. API Enhancement** | 1-2 days | Updated serializers, `include=full` parameter, validation |
| **3. Frontend Component Dev** | 3-4 days | RuleDetailDrawer, RuleEditDrawer enhancements, new hooks |
| **4. Data Population** | 2-3 days | Run population scripts, manual review, testing |
| **5. QA & Testing** | 2-3 days | End-to-end testing, edge cases, performance |
| **6. Documentation & Deploy** | 1-2 days | Update API docs, deploy to staging/production |
| **Total** | ~2-3 weeks | Full implementation |

---

## COMPARISON: Current vs Enhanced UI

### Current State (RulesList)
```
┌─────────────────────────────────────────────────────┐
│ Rule Management                                     │
├─────────────────────────────────────────────────────┤
│ 58 rules | TIG: 35, WATCH: 14, TIX: 6, EVOLVE: 3   │
│ Hard Block: 38 | Flag: 16 | Info: 4                 │
├─────────────────────────────────────────────────────┤
│ [Search...] [TIG] [WATCH] [TIX] [EVOLVE]           │
│ [hard_block] [flag] [info]                          │
├─────────────────────────────────────────────────────┤
│ Rule Key  │ Name              │ Set  │ Sev │ Active│
├───────────┼──────────────────┼──────┼─────┼──────┤
│ TIG-01    │ Minimum debt     │ TIG  │ HB  │  ✓   │
│ TIG-02    │ Min disposable   │ TIG  │ HB  │  ✓   │
│ ...       │ ...              │ ...  │ ... │ ...  │
└─────────────────────────────────────────────────────┘
```

### Enhanced State (With Documentation)
```
┌──────────────────────────────────────────────────────────────┐
│ Rule Management                                              │
├──────────────────────────────────────────────────────────────┤
│ 58 rules | TIG: 35, WATCH: 14, TIX: 6, EVOLVE: 3            │
│ Hard Block: 38 | Flag: 16 | Info: 4 | By Category: ...      │
├──────────────────────────────────────────────────────────────┤
│ [Search...] [TIG] [WATCH] [TIX] [EVOLVE]                    │
│ [Income] [Bank] [Proof] [Creditor] [HMRC] [Council]         │
│ [hard_block] [flag] [info] [Active] [Inactive]              │
├──────────────────────────────────────────────────────────────┤
│ Rule Key │ Name            │ Category │ Sev  │ Thresh │ Rev │
├──────────┼─────────────────┼──────────┼──────┼────────┼─────┤
│ TIG-01   │ Minimum debt    │ Income   │ HB   │ 6000   │ ✓   │
│ TIG-20.1 │ Creation/Sygma  │ Creditor │ HB   │  -     │ 5/22│
│ ...      │ ...             │ ...      │ ...  │ ...    │ ... │
├──────────┴─────────────────┴──────────┴──────┴────────┴─────┤
│                                          [View] [Edit] [Delete]
└──────────────────────────────────────────────────────────────┘

CLICK ROW → Detail Drawer (Read-only)
    ├── Full description & purpose
    ├── Implementation notes & example cases
    ├── Creditor-specific applicability
    ├── Related rules (clickable)
    ├── Reference links to markdown/Excel
    ├── Review history
    └── [Edit] button
    
CLICK [Edit] → Edit Drawer
    ├── All fields editable
    ├── Multi-select for related_rules
    ├── JSON editor for references
    └── [Save] [Cancel] [Delete]
```

---

## COMPLETION CHECKLIST

- [ ] Create Django migration for new fields
- [ ] Update GlobalCriteria model
- [ ] Update API serializers & views
- [ ] Create populate_rule_documentation.py script
- [ ] Create create_rule_relationships.py script
- [ ] Create RuleDetailDrawer component
- [ ] Enhance RuleEditDrawer component
- [ ] Enhance RulesList component with new filters
- [ ] Create useRuleDetail hook
- [ ] Add category filter to UI
- [ ] Add review date display
- [ ] Add threshold value units/context
- [ ] Test all CRUD operations
- [ ] Test filters & search
- [ ] Performance testing (58 rules with full data)
- [ ] Update API documentation
- [ ] Create user guide for rule management
- [ ] Deploy to staging
- [ ] QA sign-off
- [ ] Deploy to production
- [ ] Monitor & iterate

---

## SUCCESS METRICS

✅ **All 58 rules** visible and manageable in frontend  
✅ **Complete documentation** stored for each rule (description, examples, messages)  
✅ **Related rules** linked and clickable  
✅ **Category-based filtering** working smoothly  
✅ **Threshold values** displayed with context  
✅ **Creditor-specific rules** clearly marked  
✅ **Review history** tracked  
✅ **API endpoints** return full data when requested  
✅ **Performance** <200ms for list view, <100ms for detail view  
✅ **User satisfaction** — easy to find, understand, and manage rules  

---

**Next Steps:** 
1. Review this plan with stakeholders
2. Approve database schema changes
3. Begin Phase 1: Schema Migration
4. Set up development environment
5. Start implementation sprints
