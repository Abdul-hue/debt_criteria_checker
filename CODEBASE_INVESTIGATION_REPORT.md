# IVA Criteria Calculator — Comprehensive Codebase Investigation Report

**Date:** May 25, 2026  
**Scope:** Pre-implementation analysis for SFS Expenditure Guidelines feature  
**Status:** Complete — No code changes made

---

## 1. PROJECT STRUCTURE & STACK

### Framework & Language
- **Framework:** Django 6.0.4+ (djangorestframework 3.14+)
- **Python Version:** 3.12 (specified in Dockerfile)
- **Application Type:** Django REST API microservice

### Database Configuration
**Default Database (SQLite):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'db.sqlite3',
    },
```

**Aryza Remote Database (MySQL):**
```python
    'aryza': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': os.environ.get('ARYZA_DB_HOST'),
        'USER': os.environ.get('ARYZA_DB_USER'),
        'PASSWORD': os.environ.get('ARYZA_DB_PASSWORD'),
        'NAME': os.environ.get('ARYZA_DB_NAME'),
        'PORT': os.environ.get('ARYZA_DB_PORT', '3306'),
        'OPTIONS': {'connect_timeout': 10, 'ssl': {'ssl-mode': 'REQUIRE'}},
    },
}
```

### ORM & Query Layer
- **ORM:** Django ORM (no SQLAlchemy or other alternatives)
- **Pattern:** Direct model access via `Model.objects.all()`, `filter()`, `create()`, etc.
- **Query Style:** No raw SQL observed; pure ORM throughout

### Test Framework & Configuration
**Test Framework:** pytest + pytest-django  
**Test Location:** `/tests/` directory  
**Configuration File:** `pytest.ini` (project root)  
**Fixtures:** `conftest.py` with case payload fixtures (3 real cases):
```python
@pytest.fixture
def case_payloads():
    # Loads payload_324991.json, payload_332591.json, payload_349223.json
    # Specific case fixtures: theresa_topp_payload, cristian_iancu_payload, daniel_gallagher_payload
```

**Existing Tests:**
- `test_alias_map_integrity.py` — Validates CREDITOR_ALIAS_MAP
- `test_banking_groups_seed.py` — Banking group seeding
- `test_creditor_resolution.py` — Creditor name resolution
- `test_criteria_engine.py` — Core engine tests
- `test_patch_set.py` — Patch validation
- `test_which_representative_seed.py` — Representative assignment

### Docker & Containerization
**Docker Compose:** Single-service setup
```yaml
services:
  debt-criteria:
    build: .
    container_name: debt-criteria
    ports:
      - "5010:8000"
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
```

**Dockerfile:** Multi-stage build  
- Stage 1: Node.js 20 — Frontend build
- Stage 2: Python 3.12 — Django + frontend assets
- Production server: Gunicorn (3 workers, 120s timeout)
- System dependencies: build-essential, pkg-config, libmysqlclient-dev

---

## 2. EXISTING MODELS & DATABASE

### Complete Model Inventory

#### CreditorCriteria
**Purpose:** Creditor-specific voting and acceptance criteria  
**Primary Key:** `id` (BigAutoField)  
**Unique Constraint:** `creditor_name` (CharField, max_length=255, unique=True)

**Core Fields:**
```python
creditor_name = CharField(max_length=255, unique=True)
trading_names = JSONField(blank=True, null=True, default=list)
representative = CharField(max_length=15, choices=['WATCH', 'TIX', 'EVOLVE', 'EVERYDAY_LOANS', 'NONE'])
status = CharField(max_length=20, choices=['ACCEPT', 'REJECT', 'WILL_CONSIDER', 'DO_NOT_VOTE', 'CONDITIONAL_VOTER'])
min_dividend_pence = IntegerField(blank=True, null=True)
dividend_notes = TextField(blank=True, null=True)
contact_name = CharField(max_length=255, blank=True, null=True)
contact_email = EmailField(blank=True, null=True)
contact_phone = CharField(max_length=20, blank=True, null=True)
criteria_notes = TextField(blank=True, null=True)
raw_updated_criteria = CharField(max_length=255, blank=True, null=True)
source_sheet = CharField(max_length=100, blank=True, null=True)
is_active = BooleanField(default=True)
account_age_months = IntegerField(null=True, blank=True)
parent_group = CharField(max_length=255, blank=True, null=True)
```

**Rejection/Conditional Fields:**
```python
reject_if_in_dmp = BooleanField(default=False)
reject_if_never_made_payment = BooleanField(default=False)
reject_if_ie_doesnt_match_application = BooleanField(default=False)
reject_if_debt_repayable_within_months = IntegerField(blank=True, null=True)
reject_if_client_still_has_asset = BooleanField(default=False)
reject_if_majority_share_exceeds_pct = DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)
reject_if_second_iva = BooleanField(default=False)
reject_if_police_employed = BooleanField(default=False)
reject_if_equity_exceeds_debt = BooleanField(default=False)
requires_pg_called_up = BooleanField(default=False)
requires_arrangement_call_before_proposing = BooleanField(default=False)
requires_grant_overpayment_only = BooleanField(default=False)
```

**Financial & Vehicle Thresholds:**
```python
vehicle_arrears_repossession_months = IntegerField(blank=True, null=True)
fees_cap_percentage = DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)
min_di_for_fees_pence = IntegerField(blank=True, null=True)
termination_risk_if_vehicle_on_finance = BooleanField(default=False)
```

**Conditional & Flags:**
```python
conditional_voter = BooleanField(default=False)
conditional_voter_min_dividend_pence = IntegerField(blank=True, null=True)
open_banking_access = BooleanField(default=False)
fraud_claim_risk = BooleanField(default=False)
blocked_until_cleared = BooleanField(default=False)
blocked_reason = TextField(blank=True, default='')
```

**Audit:**
```python
last_reviewed = DateField(blank=True, null=True)
updated_by = ForeignKey(User, on_delete=SET_NULL, blank=True, null=True, related_name='creditor_criteria_updates')
last_updated = DateTimeField(auto_now=True)
```

**Indexes:**
```python
Index(fields=['creditor_name'])
Index(fields=['representative'])
Index(fields=['is_active'])
```

---

#### GlobalCriteria
**Purpose:** Global rules, thresholds, and documentation for all assessment rules  
**Primary Key:** `id` (BigAutoField)  
**Unique Constraint:** `rule_key` (CharField, max_length=255, unique=True)

**Core Fields:**
```python
criteria_set = CharField(max_length=10, choices=['TIG', 'WATCH', 'TIX', 'EVOLVE'])
rule_key = CharField(max_length=255, unique=True)
rule_name = CharField(max_length=255)
severity = CharField(max_length=20, choices=['hard_block', 'flag', 'info'])
is_active = BooleanField(default=True)
threshold_value = DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
```

**Documentation Fields:**
```python
description = TextField(blank=True, null=True)
action = TextField(blank=True, null=True)
implementation_notes = TextField(blank=True, null=True)
example_case = TextField(blank=True, null=True)
rejection_message = TextField(blank=True, null=True)
flag_message = TextField(blank=True, null=True)
```

**Organization Fields:**
```python
category = CharField(max_length=50, choices=['income', 'bank_statements', 'proof_of_debts', 'creditor_specific', 'hmrc', 'vehicle', 'flags', 'other'], blank=True, null=True)
is_creditor_specific = BooleanField(default=False)
applies_to_creditors = JSONField(blank=True, null=True, default=list)
execution_order = IntegerField(blank=True, null=True)
```

**Reference Fields:**
```python
references = JSONField(blank=True, null=True, default=list)
related_rules = JSONField(blank=True, null=True, default=list)
depends_on_rules = JSONField(blank=True, null=True, default=list)
```

**Review & Audit:**
```python
last_reviewed = DateField(blank=True, null=True)
review_notes = TextField(blank=True, null=True)
updated_by = ForeignKey(User, on_delete=SET_NULL, blank=True, null=True, related_name='global_criteria_updates')
last_updated = DateTimeField(auto_now=True)
```

**Indexes:**
```python
Index(fields=['rule_key'])
Index(fields=['criteria_set'])
Index(fields=['category'])
Index(fields=['is_active'])
```

---

#### CriteriaDecision
**Purpose:** Audit log and history of all assessment decisions  
**Primary Key:** `id` (UUIDField, auto-generated)  
**Indexes:** application_id (CharField, db_index=True), triggered_at (DateTimeField, db_index=True)

```python
application_id = CharField(max_length=255, db_index=True)
client_name = CharField(max_length=255)
input_snapshot = JSONField()  # Full input to engine
decision_output = JSONField()  # Full output from engine
result_json = JSONField(null=True, blank=True)  # Phase 1 standardized response
recommended_solution = CharField(max_length=20, choices=[
    'IVA', 'IVA NOT SUITABLE', 'IVA POSSIBLE', 'DMP', 'BREATHING_SPACE', 'FREE_SECTOR', 'UNCLEAR'
])
passes_all_hard_blocks = BooleanField()
triggered_by = ForeignKey(User, on_delete=SET_NULL, blank=True, null=True, related_name='criteria_decisions')
triggered_at = DateTimeField(auto_now_add=True, db_index=True)
source = CharField(max_length=20, choices=['STANDALONE', 'CASE_ASSESSMENT'])
```

---

#### CouncilRule
**Purpose:** Per-council voting behaviour and rejection conditions  
**Primary Key:** `id` (auto)  
**Unique Constraint:** `council_name` (CharField, max_length=255, unique=True)

```python
council_name = CharField(max_length=255, unique=True)
status = CharField(max_length=20, choices=['ACCEPT', 'REJECT', 'WILL_CONSIDER', 'DO_NOT_VOTE', 'CONDITIONAL_VOTER'])
min_dividend_pence = IntegerField(blank=True, null=True)
reject_if_employed = BooleanField(default=False)
reject_if_unemployed_and_homeowner = BooleanField(default=False)
reject_if_benefits_only = BooleanField(default=False)
reject_if_any_benefits = BooleanField(default=False)
reject_if_previous_iva = BooleanField(default=False)
reject_if_dro_criteria_met = BooleanField(default=False)
reject_if_aoe_in_place = BooleanField(default=False)
reject_if_joint_one_party_only = BooleanField(default=False)
reject_if_joint_both_parties = BooleanField(default=False)
reject_if_sole = BooleanField(default=False)
reject_if_joint_one_employed = BooleanField(default=False)
do_not_chase = BooleanField(default=False)
include_current_year_ct = BooleanField(default=False)
blocked_reason = TextField(blank=True, default='')
criteria_changed_from_rej_date = CharField(max_length=100, blank=True, default='')
contact_name = CharField(max_length=255, blank=True, default='')
contact_number = CharField(max_length=255, blank=True, default='')
source_priority = IntegerField(default=2)  # 1=authoritative, 2=dividends sheet
last_reviewed = DateField(blank=True, null=True)
```

---

#### CountyCouncilRouting
**Purpose:** Maps county+district combinations to CouncilRule  
**Unique Constraint:** `(county_name, district_name)`

```python
county_name = CharField(max_length=255)
district_name = CharField(max_length=255)
council_rule = ForeignKey(CouncilRule, on_delete=PROTECT, related_name='county_routings', blank=True, null=True)
```

---

#### DebtTypeCouncilVote
**Purpose:** Per-debt-type override for CouncilRule voting  
**Unique Constraint:** `(council, debt_type)`

```python
council = ForeignKey(CouncilRule, on_delete=CASCADE, related_name='debt_type_votes')
debt_type = CharField(max_length=50, choices=['COUNCIL_TAX', 'PCN', 'HOUSING_BENEFIT'])
status = CharField(max_length=20, choices=['ACCEPT', 'REJECT', 'WILL_CONSIDER', 'DO_NOT_VOTE', 'CONDITIONAL_VOTER'])
```

---

#### ConditionalVoterRule
**Purpose:** Supplementary configuration for conditional-voter CreditorCriteria  
**OneToOne:** `creditor` → CreditorCriteria

```python
creditor = OneToOneField(CreditorCriteria, on_delete=CASCADE, related_name='conditional_voter_rule')
min_dividend_pence = IntegerField(blank=True, null=True)
contact_required = BooleanField(default=False)
contact_name = CharField(blank=True, default='', max_length=255)
contact_email = EmailField(blank=True, default='', max_length=254)
```

---

#### CreditorOpenBankingRule
**Purpose:** Open-banking review requirements for CreditorCriteria  
**OneToOne:** `creditor` → CreditorCriteria

```python
creditor = OneToOneField(CreditorCriteria, on_delete=CASCADE, related_name='open_banking_rule')
review_period_months = IntegerField(default=3)
ie_must_match_exactly = BooleanField(default=False)
```

---

#### Voter
**Purpose:** Represents a creditor vote on a specific case  
**Primary Key:** `id` (BigAutoField)

```python
name = CharField(max_length=255)
is_joint = BooleanField(default=False)
last_payment_date = DateField(blank=True, null=True)
first_payment_made = BooleanField(default=False)
vehicle_arrears_months = IntegerField(blank=True, null=True)
ie_matches_loan_application = BooleanField(blank=True, null=True)
arrangement_confirmed_before_proposing = BooleanField(default=False)
client_still_has_asset_in_possession = BooleanField(default=False)
is_grant_overpayment = BooleanField(default=False)
guarantee_called_up = BooleanField(blank=True, null=True)

@property
def months_since_last_payment(self):  # Calculated property
```

---

#### Application
**Purpose:** Debt application submitted for assessment  
**Primary Key:** `id` (BigAutoField)

```python
aryza_reference = CharField(max_length=255, unique=True)
client_name = CharField(max_length=255)
created_at = DateTimeField(auto_now_add=True)
```

---

#### ClientFlags
**Purpose:** Per-application client situation flags  
**OneToOne:** `application` → Application

```python
application = OneToOneField(Application, on_delete=CASCADE, related_name='client_flags')
is_currently_in_dmp = BooleanField(default=False)
is_royal_mail_employee = BooleanField(default=False)
is_police_officer = BooleanField(default=False)
previous_iva_failed = BooleanField(default=False)
```

---

#### EvidenceLedger
**Purpose:** Audit log of evidence and decisions  
**Primary Key:** `id` (BigAutoField)

```python
application = ForeignKey(Application, on_delete=CASCADE, related_name='evidence')
entry_type = CharField(max_length=50)
created_at = DateTimeField(auto_now_add=True)
```

---

#### CreditorResolutionMiss
**Purpose:** Tracking creditor name resolution misses for manual review  
**Primary Key:** `id` (auto)

```python
raw_name = CharField(max_length=500)
normalised_name = CharField(max_length=500, blank=True)
case_reference = CharField(max_length=100)
client_name = CharField(max_length=300, blank=True)
balance = DecimalField(max_digits=12, decimal_places=2, null=True)
logged_at = DateTimeField(auto_now_add=True)
resolved = BooleanField(default=False)
resolution_notes = CharField(max_length=500, blank=True)

Indexes:
  Index(fields=['raw_name'])
  Index(fields=['resolved', 'logged_at'])
```

---

### Models Related to Expenses/Household/Budget
**Currently: NONE**

There are **no existing models** for:
- Household composition (dependants, adults, children)
- Expense categories or guidelines
- Expenditure types or reference amounts
- SFS-specific data structures

However, the engine **accepts** structured expense data:
```python
# In case_data dict passed to assess_case():
"expenditure": {k: v/100.0 for k, v in case_data_obj.expenditure.items()},
"sfs_expenditure_breakdown": case_data_obj.sfs_expenditure_breakdown,
"dependants": case_data_obj.dependants,
```

These are currently **dictionaries**, not models.

---

### Migration History Summary
**Total Migrations:** 41 (0001_initial.py through 0041_add_breathing_space_choice.py)

**Key Phases:**
- **0001-0002:** Initial schema + CriteriaDecision
- **0003-0008:** Refinements (remove booleans, add account_age, seed data)
- **0009-0010:** Phase 2 schema expansion
- **0011-0012:** Phase 3 Voter fields + ClientFlags
- **0013+:** Incremental seeding and fixes

**Most Recent Migrations:**
- 0040: GlobalCriteria action field
- 0041: Add BREATHING_SPACE choice to CriteriaDecision

---

### Primary Key & Timestamp Conventions
- **Primary Key Type:** `BigAutoField` (set globally in settings.py as DEFAULT_AUTO_FIELD)
- **Timestamps:** 
  - `auto_now_add=True` for creation (created_at, triggered_at, logged_at)
  - `auto_now=True` for updates (last_updated)
  - Manual `DateField` for last_reviewed

---

## 3. EXISTING API LAYER

### REST Framework Configuration
```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/min',
        'assess': '1000/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

---

### Complete API Endpoint Listing

**URL Prefix:** `/api/v1/criteria/`  
**Base URL:** `http://localhost:5010/api/`

#### Assessment Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| POST | `/assess/` | `AssessCaseView` | JWT | IsAuthenticated | Run criteria assessment |
| GET | `/assess/history/` | `AssessHistoryView` | JWT | IsAdminUser | List historical decisions |
| GET | `/assess/history/{id}/` | `AssessHistoryDetailView` | JWT | IsAdminUser | Get decision detail |
| DELETE | `/assess/history/{id}/` | `AssessHistoryDetailView` | JWT | IsAdminUser | Delete decision |

#### Creditor Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/creditors/` | `CreditorListView` | JWT | IsAdminUser | List creditors (paginated) |
| POST | `/creditors/` | `CreditorListView` | JWT | IsAdminUser | Create creditor |
| GET | `/creditors/{id}/` | `CreditorDetailView` | JWT | IsAdminUser | Get creditor detail |
| PUT | `/creditors/{id}/` | `CreditorDetailView` | JWT | IsAdminUser | Update creditor |
| PATCH | `/creditors/{id}/` | `CreditorDetailView` | JWT | IsAdminUser | Partial update |
| DELETE | `/creditors/{id}/` | `CreditorDetailView` | JWT | IsAdminUser | Delete creditor |

#### Rules Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/rules/` | `RulesListView` | JWT | IsAdminUser | List all rules |
| POST | `/rules/` | `RulesListView` | JWT | IsAdminUser | Create rule |
| GET | `/rules/{rule_key}/` | `RulesDetailView` | JWT | IsAdminUser | Get rule by key |
| PUT | `/rules/{rule_key}/` | `RulesDetailView` | JWT | IsAdminUser | Update rule |
| PATCH | `/rules/{rule_key}/` | `RulesDetailView` | JWT | IsAdminUser | Partial update |
| DELETE | `/rules/{rule_key}/` | `RulesDetailView` | JWT | IsAdminUser | Delete rule |
| GET | `/rules/{rule_key}/history/` | `RuleHistoryView` | JWT | IsAdminUser | Rule change history |

#### Council Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/councils/` | `CouncilRuleListView` | JWT | IsAdminUser | List councils |
| POST | `/councils/` | `CouncilRuleListView` | JWT | IsAdminUser | Create council rule |
| GET | `/councils/{pk}/` | `CouncilRuleDetailView` | JWT | IsAdminUser | Get council |
| PUT | `/councils/{pk}/` | `CouncilRuleDetailView` | JWT | IsAdminUser | Update council |
| PATCH | `/councils/{pk}/` | `CouncilRuleDetailView` | JWT | IsAdminUser | Partial update |
| DELETE | `/councils/{pk}/` | `CouncilRuleDetailView` | JWT | IsAdminUser | Delete council |

#### Application Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/applications/` | `ApplicationListView` | JWT | IsAdminUser | List applications |
| POST | `/applications/` | `ApplicationListView` | JWT | IsAdminUser | Create application |
| GET | `/applications/{pk}/` | `ApplicationDetailView` | JWT | IsAdminUser | Get application |
| PUT | `/applications/{pk}/` | `ApplicationDetailView` | JWT | IsAdminUser | Update application |
| DELETE | `/applications/{pk}/` | `ApplicationDetailView` | JWT | IsAdminUser | Delete application |

#### Evidence Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/evidence/` | `EvidenceLedgerListView` | JWT | IsAdminUser | List evidence |
| GET | `/evidence/{pk}/` | `EvidenceLedgerDetailView` | JWT | IsAdminUser | Get evidence |

#### Voter Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/voters/` | `VoterListView` | JWT | IsAdminUser | List voters |
| GET | `/voters/{pk}/` | `VoterDetailView` | JWT | IsAdminUser | Get voter |

#### User Endpoints
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/users/` | `UserListView` | JWT | IsAdminUser | List users |
| GET | `/users/{pk}/` | `UserDetailView` | JWT | IsAdminUser | Get user |

#### Evaluation Endpoints (Phase 7)
| HTTP | Path | View Class | Auth | Permissions | Purpose |
|------|------|-----------|------|-----------|---------|
| GET | `/cases/{case_id}/evaluate` | `EvaluateCaseView` | JWT | IsAuthenticated | Evaluate case |
| GET | `/cases/{case_id}/evaluations` | `EvaluationHistoryView` | JWT | IsAuthenticated | Evaluation history |

#### Authentication Endpoints
| HTTP | Path | Handler | Purpose |
|------|------|---------|---------|
| POST | `/api/token/` | `email_token_obtain_pair` | Obtain JWT (email-based) |
| POST | `/api/token/username/` | `TokenObtainPairView` | Obtain JWT (username) |
| POST | `/api/token/refresh/` | `TokenRefreshView` | Refresh JWT token |

---

### Authentication & Permissions Model

**Authentication Method:** JWT (rest_framework_simplejwt)  
**Token Type:** Bearer token in Authorization header
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Permission Classes Used:**
- `IsAuthenticated` — Any authenticated user (most endpoints)
- `IsAdminUser` — User.is_staff=True (admin-only endpoints like CreditorListView)
- No custom permissions; relies on Django's built-in User model

**Throttling:**
- Scope: `UserRateThrottle` 
- Rates: `'user': '1000/min'`, `'assess': '1000/min'`
- Custom throttle class: `AssessRateThrottle(UserRateThrottle)` with scope='assess'

---

### API Response Serialization

**No DRF Serializers Used.** Instead, manual dict-to-JSON conversion:

**Pattern 1: Model to Dict Function**
```python
def _creditor_to_dict(creditor):
    return {
        "id": creditor.id,
        "creditor_name": creditor.creditor_name,
        "trading_names": creditor.trading_names,
        # ... all fields ...
    }
```

**Pattern 2: Response Building**
```python
return Response({
    "count": paginator.count,
    "next": "...",
    "previous": "...",
    "results": [_creditor_to_dict(c) for c in page_obj],
}, status=status.HTTP_200_OK)
```

**Pattern 3: Engine Output Serialization**
```python
def build_phase7_response_fields(result: dict) -> dict:
    """Serialize assess_case result into JSON-safe dict"""
    def _serialise_value(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, set):
            return list(v)
        return v
    
    return {
        "overall": result.get("overall"),
        "hard_blocks": _rules(result.get("hard_blocks", [])),
        "flags": _rules(result.get("flags", [])),
        "creditor_positions": [
            {**pos, "balance": float(pos["balance"]) if isinstance(pos["balance"], Decimal) else pos["balance"]}
            for pos in result.get("creditor_positions", [])
        ],
        # ... more fields ...
    }
```

---

## 4. IVA CRITERIA CALCULATION ENGINE

### Core Purpose
Multi-phase debt assessment engine that evaluates whether a case is suitable for an Individual Voluntary Arrangement (IVA) against 58+ configurable rules covering:
- Income sufficiency
- Expense verification
- Creditor-specific conditions
- Council voting behaviour
- Household composition
- Asset and debt analysis

### Main Entry Point
```python
def assess_case(case_data: dict) -> dict:
    """
    Evaluates case data against all active rules.
    
    Args:
        case_data: Dictionary with keys:
          - application_id, client_name, clientInfo
          - employment_status, disposable_income, total_unsecured_debt
          - income: dict with component amounts (pence → converted to £)
          - expenditure: dict with category amounts (pence → converted to £)
          - creditors: list of creditor dicts
          - property: dict with owns_property, value, equity, mortgage_balance
          - vehicle: dict with has_vehicle, value, hp_monthly_payment
          - sfs_expenditure_breakdown: dict (SFS guidelines data)
          - gold_transactions: dict
          - flags: dict with client flags
          - evidence_ledger: list of verified evidence
          - dependants: dict with household composition
    
    Returns:
        Dictionary with keys:
          - overall_status: "ELIGIBLE" | "INELIGIBLE" | "REFERRED"
          - passes_all_hard_blocks: bool
          - tig_eligible: bool
          - hard_blocks: [RuleResult, ...]
          - flags: [RuleResult, ...]
          - info: [RuleResult, ...]
          - passed: [RuleResult, ...]
          - creditor_positions: [creditor analysis]
          - council_positions: [council analysis]
          - majority_analysis: dict
          - dividend_analysis: dict
          - representatives_detected: set of representative names
    """
```

### Case Data Structure
The engine accepts case data with the following financial structure:

```python
case_data = {
    # Client & Application Info
    "application_id": "324991",
    "client_name": "John Doe",
    "clientInfo": {"dateOfBirth": "1970-01-01", "client_name": "John Doe"},
    "employment_status": "employed" | "self_employed" | "unemployed" | "retired" | "benefits",
    
    # Financial Summary
    "disposable_income": 500.50,  # £ per month
    "total_unsecured_debt": 15000.00,  # Total £
    "financial_summary": {
        "net_balance": 500.50,
        "total_income": 2500.00,
        "income_source": "employed"
    },
    
    # Income (pence → £)
    "income": {
        "total": 250000,  # 2500.00 £
        "employment": 200000,
        "universal_credit": 30000,
        "dla": 0,
        "pip": 20000,
        "other_benefits": 0,
        "third_party_contribution": 0,
        "benefit_income_amount": 50.00,  # Aggregated benefits
    },
    
    # Expenditure (pence → £)
    "expenditure": {
        "total": 180000,  # 1800.00 £
        "rent": 100000,
        "utilities": 15000,
        "food": 25000,
        "transport": 20000,
        "childcare": 10000,
        "insurance": 10000,
        # ... category breakdown
    },
    
    # SFS-SPECIFIC DATA (NEW)
    "sfs_expenditure_breakdown": {
        "rent": 100000,
        "utilities": 15000,
        # ... SFS guideline categories
    },
    
    # Creditors
    "creditors": [
        {
            "creditor_name": "NatWest",  # Resolved via CREDITOR_ALIAS_MAP
            "original_name": "natwest group plc",  # Raw Aryza name
            "balance": 5000.00,
            "type": "credit_card",
            # ... more fields
        }
    ],
    
    # Property
    "property": {
        "owns_property": True,
        "property_value": 300000.00,
        "mortgage_balance": 150000.00,
        "equity": 150000.00,
    },
    
    # Vehicle
    "vehicle": {
        "has_vehicle": True,
        "vehicle_value": 15000.00,
        "hp_monthly_payment": 350.00,
    },
    
    # Household (SFS-related)
    "dependants": {
        "adults": 1,
        "children": 2,
        "total": 3,
    },
    
    # Additional Data
    "gold_transactions": {...},
    "flags": {
        "is_currently_in_dmp": False,
        "is_royal_mail_employee": False,
        "is_police_officer": False,
        "previous_iva_failed": False,
        "previous_iva_failed_reason": None,
    },
    "evidence_ledger": [
        {"category": "wage_slips", "is_verified": True, "ref": "..."},
        {"category": "bank_statement", "is_verified": True, "ref": "..."},
    ],
}
```

### RuleResult Dataclass
```python
@dataclass
class RuleResult:
    rule_id: str                           # "TIG-01", "WATCH-22.1", etc.
    severity: str                          # "hard_block" | "flag" | "info" | "pass"
    triggered: bool                        # True if rule condition met
    message: str                           # Human-readable explanation
    threshold: Optional[float] = None      # For numeric comparisons
    actual_value: Optional[float] = None   # Actual case value
```

### Current Output Structure
```python
{
    "overall_status": "ELIGIBLE" | "INELIGIBLE" | "REFERRED",
    "passes_all_hard_blocks": true,
    "tig_eligible": true,
    
    "hard_blocks": [
        {
            "rule_id": "TIG-01",
            "severity": "hard_block",
            "triggered": false,
            "message": "...",
            "threshold": 500,
            "actual_value": 450,
            "title": "Rule name from DB",
            "description": "From GlobalCriteria",
            "action": "From GlobalCriteria"
        }
    ],
    
    "flags": [...similar structure...],
    "info": [...similar structure...],
    "passed": [...similar structure...],
    
    "creditor_positions": [
        {
            "creditor_name": "NatWest",
            "resolved_canonical_name": "NatWest",
            "original_aryza_name": "natwest group plc",
            "effective_status": "ACCEPT" | "REJECT" | "DO_NOT_VOTE",
            "findings": ["CREDITOR-MAJORITY-SHARE-EXCEEDED"],
            "reason": "Explanation",
            "balance": 5000.00,
        }
    ],
    
    "council_positions": [...],
    
    "majority_analysis": {
        "total_debt": 15000.00,
        "single_creditor_limit_pct": 33,
        "creditor": "NatWest",
        "share_pct": 33.33,
        "exceeded": false,
    },
    
    "dividend_analysis": {...},
    "representatives_detected": ["WATCH", "TIX"],
}
```

---

### Existing Expenditure Handling

**Current State:**
- Expenditure is passed in as a simple dict `{"category": amount_in_pounds, ...}`
- No model-based storage
- No per-category "guideline limit" comparison
- Used only for disposable income calculation (income - expenditure)

**No existing concept of:**
- ❌ Expenditure guideline categories
- ❌ SFS guideline limits per category
- ❌ Household-size adjustment factors
- ❌ Age-of-dependant adjustments
- ❌ Regional variations

---

## 5. SERIALIZATION LAYER

### Approach: Manual Dict-to-JSON (No DRF Serializers)

The project **does not use DRF Serializers** anywhere. All serialization is manual.

### Example: Creditor Serialization
```python
def _creditor_to_dict(creditor):
    """Convert CreditorCriteria model instance to dict for JSON response"""
    return {
        "id": creditor.id,
        "creditor_name": creditor.creditor_name,
        "trading_names": creditor.trading_names,
        "representative": creditor.representative,
        "status": creditor.status,
        # ... 40+ more fields ...
        "last_updated": creditor.last_updated.isoformat(),
    }
```

**Usage in view:**
```python
class CreditorListView(APIView):
    def get(self, request):
        queryset = CreditorCriteria.objects.all().order_by('creditor_name')
        # ... filtering ...
        return Response({
            "count": paginator.count,
            "results": [_creditor_to_dict(c) for c in page_obj],
        }, status=status.HTTP_200_OK)
```

### Example: Rules Enrichment (Nested Lookup)
```python
def enrich_rules_with_meta(rule_list):
    """
    Takes RuleResult objects, fetches GlobalCriteria metadata,
    returns enriched dicts.
    """
    rule_keys = [r.rule_id if hasattr(r, 'rule_id') else r.get('rule_id') for r in rule_list]
    
    criteria = GlobalCriteria.objects.filter(rule_key__in=rule_keys).values(
        'rule_key', 'rule_name', 'description', 'action'
    )
    meta_map = {c['rule_key']: c for c in criteria}
    
    enriched = []
    for r in rule_list:
        rid = r.rule_id if hasattr(r, 'rule_id') else r.get('rule_id')
        meta = meta_map.get(rid, {})
        
        r_dict = {...}
        r_dict.update({
            'title': meta.get('rule_name') or rid,
            'description': meta.get('description'),
            'action': meta.get('action'),
        })
        enriched.append(r_dict)
    
    return enriched
```

---

## 6. CONFIGURATION & SETTINGS

### Full INSTALLED_APPS
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'debt_app',
]
```

### Full REST_FRAMEWORK Config
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/min',
        'assess': '1000/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

### CORS Configuration
```python
CORS_ALLOW_ALL_ORIGINS = True
```

### Security & Session Settings
```python
SECURE_CROSS_ORIGIN_OPENER_POLICY = None
SESSION_COOKIE_SECURE = False  # Non-HTTPS environment
CSRF_COOKIE_SECURE = False
```

### Static Files
```python
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'
STATICFILES_DIRS = [BASE_DIR / 'frontend' / 'dist']

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

### Database Configuration (Detailed)
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'db.sqlite3',
    },
    'aryza': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': os.environ.get('ARYZA_DB_HOST'),
        'USER': os.environ.get('ARYZA_DB_USER'),
        'PASSWORD': os.environ.get('ARYZA_DB_PASSWORD'),
        'NAME': os.environ.get('ARYZA_DB_NAME'),
        'PORT': os.environ.get('ARYZA_DB_PORT', '3306'),
        'OPTIONS': {
            'connect_timeout': 10,
            'ssl': {'ssl-mode': 'REQUIRE'},
        },
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
```

### Environment Variables Detected
**From settings.py:**
```
SECRET_KEY          (default: 'dev-key')
DEBUG               (default: 'False')
ALLOWED_HOSTS       (default: '*')
ARYZA_DB_HOST
ARYZA_DB_USER
ARYZA_DB_PASSWORD
ARYZA_DB_NAME
ARYZA_DB_PORT       (default: '3306')
```

**Project loads via:**
```python
load_dotenv(BASE_DIR / '.env')
```

Expected `.env` file in project root (not provided in repo).

### Middleware Stack
```python
MIDDLEWARE = [
    'debt_project.debug_middleware.RequestDebugMiddleware',  # Custom
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

---

## 7. SEED DATA & FIXTURES

### Management Commands Directory
Location: `debt_app/management/commands/`

**Command Listing:**

| Command | Purpose |
|---------|---------|
| `discover_aryza.py` | Discover and sync creditors from Aryza database |
| `fix_unknown_creditor_statuses.py` | Bulk fix status for unresolved creditors |
| `review_unknown_creditors.py` | Interactive review of unknown creditors |
| `seed_admin.py` | Create initial admin user |
| `seed_all_councils.py` | Seed all UK councils from data source |
| `seed_creditor_criteria.py` | Load creditor criteria from Excel sheets |
| `seed_dividends.py` | Load dividend thresholds |
| `seed_rule_meta.py` | Populate GlobalCriteria documentation |
| `validate_alias_map.py` | Validate CREDITOR_ALIAS_MAP integrity |

### Fixture Files
Location: `debt_app/fixtures/`

**Directory exists but fixtures not detailed in investigation.**

### Deployment & Initialization
**No Makefile found.** Initialization steps likely:
```bash
python manage.py migrate
python manage.py seed_admin
python manage.py seed_creditor_criteria
python manage.py seed_all_councils
python manage.py seed_rule_meta
```

---

## 8. TESTING

### Test Structure
**Location:** `/tests/` directory (root level)

**Test Files:**
```
tests/
  conftest.py                          # pytest fixtures
  test_alias_map_integrity.py          # CREDITOR_ALIAS_MAP validation
  test_banking_groups_seed.py          # Banking group seeds
  test_creditor_resolution.py          # Creditor name resolution
  test_criteria_engine.py              # Core engine tests
  test_patch_set.py                    # Patch validation
  test_which_representative_seed.py    # Representative assignment
  debug_gambling.py                    # Gambling rule debugging
  verify_tig10.py                      # TIG-10 verification
```

### Test Configuration
**pytest.ini (project root):**
```ini
[pytest]
# Configuration not shown in investigation
```

### Fixtures (conftest.py)
```python
@pytest.fixture
def case_payloads():
    """Loads real case JSON payloads from files"""
    # payload_324991.json (Theresa Topp)
    # payload_332591.json (Cristian Iancu)
    # payload_349223.json (Daniel Gallagher)

@pytest.fixture
def theresa_topp_payload(case_payloads):
    return case_payloads.get('324991')

@pytest.fixture
def cristian_iancu_payload(case_payloads):
    return case_payloads.get('332591')

@pytest.fixture
def daniel_gallagher_payload(case_payloads):
    return case_payloads.get('349223')
```

### Test Runner
```bash
pytest                  # Run all tests
pytest -v              # Verbose
pytest tests/test_*.py # Run specific test file
```

---

## 9. ADMIN INTERFACE

### Django Admin: ENABLED ✓

**Location:** `/admin/`  
**Authentication:** Django auth (separate from JWT API)

### Registered ModelAdmin Classes

**debt_app/admin.py:**

```python
@admin.register(CreditorCriteria)
class CreditorCriteriaAdmin(admin.ModelAdmin):
    list_display = ['creditor_name', 'representative', 'parent_group', 'is_active', 'last_updated']
    list_filter = ['is_active', 'representative']
    search_fields = ['creditor_name', 'trading_names', 'parent_group']
    readonly_fields = ['last_updated']

@admin.register(GlobalCriteria)
class GlobalCriteriaAdmin(admin.ModelAdmin):
    list_display = ['rule_key', 'rule_name', 'criteria_set', 'severity', 'is_active', 'last_updated']
    list_filter = ['criteria_set', 'severity']
    search_fields = ['rule_key', 'rule_name']
    readonly_fields = ['last_updated']

@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['aryza_reference', 'client_name', 'created_at']
    search_fields = ['aryza_reference', 'client_name']

@admin.register(EvidenceLedger)
class EvidenceLedgerAdmin(admin.ModelAdmin):
    list_display = ['application', 'entry_type', 'created_at']
    list_filter = ['entry_type', 'created_at']
    search_fields = ['application__client_name']

@admin.register(CriteriaDecision)
class CriteriaDecisionAdmin(admin.ModelAdmin):
    list_display = ['application_id', 'client_name', 'recommended_solution', 'passes_all_hard_blocks', 'source', 'triggered_at']
    list_filter = ['recommended_solution', 'source', 'passes_all_hard_blocks', 'triggered_at']
    search_fields = ['application_id', 'client_name']
    readonly_fields = ['id', 'triggered_at', 'input_snapshot', 'decision_output']
```

---

## 10. DEPENDENCY ON OTHER SERVICES

### External Service Dependencies

#### Aryza Database Connection
**Type:** Remote MySQL database  
**Location:** Configurable via environment variables  
**Auth:** Separate credentials  
**Usage:** Case data source  
**Client:** `debt_app/aryza_client.py` module

**Error Handling:**
```python
class AryzaCaseNotFoundError(Exception): pass
class AryzaConnectionError(Exception): pass
class AryaTimeoutError(Exception): pass
class AryzaDataError(Exception): pass
```

#### API Gateway / Shared Authentication
**Type:** None detected  
**JWT Secret:** Individual per environment (from SECRET_KEY env var)
**Shared User Table:** Django default auth.User (could be shared if DB is shared)

### Database Separation
- **Case Assessment (debt_app):** SQLite (`data/db.sqlite3`) — standalone
- **Aryza CRM Data:** Remote MySQL — completely separate
- **No shared database** between services
- **Read-only relationship:** debt_app reads from Aryza, doesn't write

### API Gateway Pattern
**Type:** Django views directly handle requests  
**No service registry** detected  
**No mesh/gateway** layer  
**Direct REST endpoints** at `/api/v1/criteria/...`

### Shared Code/Models
**Abstract Models:** None detected  
**Shared Model Inheritance:** No cross-service inheritance  
**Each service is independent** with own models

---

## INTEGRATION NOTES

### Naming Conflicts
**⚠️ POTENTIAL CONFLICTS:**
- ✓ `ExpenditureGuideline` — No existing model
- ✓ `GuidelineCategory` — No existing model
- ✓ `SFSGuideline` — No existing model
- ❌ **Model naming convention:** Must follow PascalCase pattern (e.g., `ExpenditureGuideline` not `expenditure_guideline`)

### Missing Dependencies
**Check requirements.txt — all needed packages present:**
- ✓ Django 6.0.4+
- ✓ djangorestframework
- ✓ djangorestframework-simplejwt
- ✓ python-dotenv
- ✓ rapidfuzz
- ✓ openpyxl (if SFS data is in Excel)
- ✓ mysqlclient

**No additional packages needed** for basic guideline implementation.

### Required Settings Changes
**NONE REQUIRED** for basic SFS guidelines — existing JWT auth and permissions work as-is.

**Optional:** Add SFS_EXPENDITURE settings constant if needed:
```python
SFS_EXPENDITURE_CATEGORIES = {
    'rent': {'min': 0, 'max': 1500, 'adjustable': True},
    'utilities': {'min': 50, 'max': 300, 'adjustable': False},
    # ...
}
```

### File Paths for New Code

| File Type | Path | Notes |
|-----------|------|-------|
| **Models** | `debt_app/models.py` | Add new models at end |
| **Views** | `debt_app/views/criteria_views.py` | Add new APIView classes |
| **URLs** | `debt_app/urls_criteria.py` | Register new endpoints |
| **Admin** | `debt_app/admin.py` | Register @admin.register decorators |
| **Management** | `debt_app/management/commands/` | Add seed/validation commands |
| **Tests** | `tests/test_sfs_guidelines.py` | New test file |
| **Migrations** | `debt_app/migrations/0042_*.py` | Auto-generated by makemigrations |

### Permission & Authentication Compatibility

**Incoming Permission Model:**
- IsAuthenticated — General authenticated users
- IsAdminUser — Staff users

**Existing Pattern:**
```python
class AssessCaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AssessRateThrottle]
```

**Compatibility:** ✓ PERFECT MATCH  
**No conflicts** — use same pattern for SFS endpoints.

### Conflict Resolution Pattern

**Creditor-based vs. Household-based Guidelines:**
- `CreditorCriteria` is per-creditor (granular)
- `ExpenditureGuideline` should be per-household-size + income-band (global reference)
- **No conflict:** Different domains

**Income vs. Expenditure:**
- Income: Currently dict in case_data
- Expenditure: Currently dict in case_data + potential sfs_expenditure_breakdown
- **Design:** Store SFS guideline limits in `ExpenditureGuideline` model; compare at runtime

---

## ARCHITECTURAL PATTERNS & CONVENTIONS

### View Pattern
All views extend `APIView` (not ViewSets):
```python
class MyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        # ... handle GET
        return Response({...}, status=status.HTTP_200_OK)
    
    def post(self, request):
        # ... handle POST
        return Response({...}, status=status.HTTP_201_CREATED)
```

### Serialization Pattern
No DRF Serializers. Instead:
```python
def _model_to_dict(instance):
    return {"field": instance.field, ...}

def get(self, request):
    queryset = Model.objects.all()
    return Response({
        "results": [_model_to_dict(obj) for obj in queryset]
    })
```

### Error Response Pattern
```python
def error_response(message: str, code: str, status_code: int):
    return Response(
        {"success": False, "error": message, "code": code},
        status=status_code
    )
```

### Financial Data Handling
- All monetary values in **pence (integers)** in database/input
- All calculations in **pounds (floats)** in code
- Conversion: `pence / 100.0 = pounds`

---

## SUMMARY FOR IMPLEMENTATION

✅ **Investigation Complete**

**Ready to Implement:**
1. 3 new models (ExpenditureGuideline, GuidelineCategory, SFSGuideline)
2. API endpoints (CRUD for guidelines)
3. Guideline comparison logic in assess_case()
4. Admin interface registrations
5. Management command for seeding SFS data
6. Tests for guideline validation

**Key Considerations:**
- No serializers needed (follow existing manual dict pattern)
- JWT auth already configured
- Permission system aligned (use IsAdminUser for admin endpoints)
- Naming conventions: PascalCase models, snake_case fields
- Financial data: store in pence, convert to pounds at use
- No new dependencies needed
- Migrations will auto-generate

---

**End of Investigation Report**
