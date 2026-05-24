# CRITERIA MANAGEMENT SYSTEM - EXECUTIVE SUMMARY

## Current Status: ✅ VERIFIED

| Rule | Database | Status |
|------|----------|--------|
| **TIG-20.1** (Creation Sygma Laser) | ✅ Present | CONFIRMED |
| **All 58 Rules** | ✅ Present | VERIFIED |
| **Frontend UI** | ✅ Functional | Rules Page Live |
| **API Endpoints** | ✅ Functional | /api/rules/ exists |

---

## The Plan (3-Week Implementation)

### PHASE 1: EXPAND DATABASE (Days 1-2)

**Add 15 New Fields to GlobalCriteria:**

```
Documentation Fields:
├── description              (What the rule does)
├── implementation_notes      (Technical details)
├── example_case            (When it applies)
├── rejection_message       (User message if fails)
└── flag_message            (User message if warning)

Organization Fields:
├── category                (Income/Bank/Proof/Creditor/HMRC/etc)
├── is_creditor_specific    (Yes/No)
├── applies_to_creditors    (Shop Direct, Creation, Link, etc.)
└── execution_order         (Which rule runs first)

Reference Fields:
├── references              (Links to markdown/Excel)
├── related_rules          (Linked rule keys)
└── depends_on_rules       (Rule dependencies)

Review Fields:
├── last_reviewed          (Date)
└── review_notes           (Admin notes)
```

### PHASE 2: ENHANCE API (Days 3-4)

**New Endpoints:**
```
GET /api/rules/                    # List all (basic or full)
GET /api/rules/?include=full       # Full data with documentation
GET /api/rules/<rule_key>/         # Single rule (full details)
PUT /api/rules/<rule_key>/         # Update any field
POST /api/rules/                   # Create new rule
DELETE /api/rules/<rule_key>/      # Delete rule
```

### PHASE 3: BUILD FRONTEND UI (Days 5-8)

**New Components:**
```
RulesList (Enhanced)
├── Statistics with category breakdown
├── Filters: Category + Severity + Criteria Set
├── Table with: Key | Name | Category | Severity | Threshold | Review
└── Row click → Detail Drawer

RuleDetailDrawer (NEW - Read-Only)
├── Complete rule information
├── Description & purpose
├── Example cases
├── Related rules (clickable)
├── References & documentation links
├── Review history
└── [Edit] button

RuleEditDrawer (Enhanced)
├── Edit all 15 new fields
├── Form validation
├── Multi-select for related_rules
├── JSON editor for references
└── [Save] [Cancel] [Delete]
```

### PHASE 4: POPULATE DATA (Days 9-11)

**Data Source:** Markdown + Excel criteria sheets

```
From: TIG_Criteria.md, Watch_Criteria.md, TIX_Criteria.md, Evolve_Criteria.md
Extract: Descriptions, examples, messages, categories
Populate: All 58 rules with complete documentation
Link: Related rules (e.g., TIG-01 ↔ TIG-02)
Review: Verify accuracy, set last_reviewed dates
```

### PHASE 5: QA & DEPLOY (Days 12-15)

```
Testing:
├── All CRUD operations work
├── Filters function correctly
├── Related rule links navigate properly
├── Performance: <200ms list, <100ms detail
├── Search works across all fields
└── No broken references

Deploy:
├── Database migration
├── API updates
├── Frontend bundle
└── Monitor production
```

---

## BEFORE vs AFTER Comparison

### BEFORE (Current)
```
Rules Page shows:
├── Rule Key (TIG-01)
├── Name (Minimum debt)
├── Criteria Set (TIG)
├── Severity (hard_block)
├── Active/Inactive toggle
└── Actions (Edit/Delete)

❌ No context/documentation
❌ No examples
❌ No related rules visible
❌ No category organization
❌ No threshold explanation
```

### AFTER (Enhanced)
```
Rules Page shows:
├── Rule Key + Name + Category
├── Description + Purpose (in detail view)
├── Example case scenarios
├── Related rules (clickable)
├── Threshold value with units
├── Review date + reviewer notes
├── Creditor applicability
├── References to source docs
└── Full edit capability

✅ Complete documentation
✅ Context for every rule
✅ Easy navigation
✅ Category-based organization
✅ Review tracking
✅ Source traceability
```

---

## Database Schema Changes

### Current Columns
```
id (PK)
rule_key (unique)
rule_name
criteria_set
severity
is_active
threshold_value
updated_by (FK)
last_updated
```

### NEW Columns (to add)
```
description                 ← What the rule validates
implementation_notes        ← Technical implementation
category                    ← For organization (Income/Bank/etc)
example_case               ← Real-world scenario
rejection_message          ← User-facing message
flag_message               ← Warning message
is_creditor_specific       ← Boolean flag
applies_to_creditors       ← JSON array
references                 ← JSON array (doc links)
execution_order            ← Evaluation priority
depends_on_rules           ← JSON array (dependencies)
related_rules              ← JSON array (links)
last_reviewed              ← Date
review_notes               ← Admin notes
```

---

## File Changes Required

### Backend
```
debt_app/
├── models.py              [MODIFY] Add 15 fields to GlobalCriteria
├── migrations/            [CREATE] New migration file
└── views/
    └── criteria_views.py  [MODIFY] Update serializer & query params
```

### Frontend
```
frontend/src/
├── components/rules/
│   ├── RulesList.jsx                [MODIFY] Add filters & columns
│   ├── RuleDetailDrawer.jsx         [CREATE] New component
│   ├── RuleEditDrawer.jsx           [MODIFY] Add new fields
│   └── hooks/useRuleDetail.js       [CREATE] New hook
└── pages/
    └── RulesPage.jsx                [MINOR] Pass new props
```

### Scripts
```
scripts/
├── populate_rule_documentation.py   [CREATE] Load markdown data
├── create_rule_relationships.py     [CREATE] Link related rules
└── populate_categories.py           [CREATE] Assign categories
```

---

## Data Source Mapping

### From Markdown → Database

```
TIG_Criteria.md
├── Core Requirements     → Category: "income"
├── Income Requirements   → Category: "income"
├── Bank Statements      → Category: "bank_statements"
├── Proof of Debts       → Category: "proof_of_debts"
├── HMRC Rules           → Category: "hmrc"
├── Watch Flags          → Category: "flags"
└── Creditor Specific    → Category: "creditor_specific"
                          + applies_to_creditors: [...]

Watch_Criteria.md
├── Rejection Rules      → Severity: "hard_block"
├── Modification Rules   → Severity: "flag"
└── Additional           → Severity: "info"

TIX_Criteria.md
├── Rejection Rules      → Category: "creditor_specific"
├── Modifications        → Category: "vehicle"
└── Updates              → Category: "other"

Evolve_Criteria.md
├── Rejection Rules      → Category: "creditor_specific"
└── Notes                → Category: "other"
```

---

## API Changes Example

### Current Response
```json
{
  "rule_key": "TIG-20.1",
  "name": "Creation Sygma Laser hard block",
  "criteria_set": "TIG",
  "severity": "hard_block",
  "is_active": true,
  "threshold_value": null
}
```

### Enhanced Response (?include=full)
```json
{
  "rule_key": "TIG-20.1",
  "name": "Creation Sygma Laser hard block",
  "criteria_set": "TIG",
  "severity": "hard_block",
  "is_active": true,
  "threshold_value": null,
  
  "description": "Prevents IVA proposal if client has Creation/Sygma/Laser account with spending in last 3-4 months",
  "category": "creditor_specific",
  "example_case": "Client has Very (Shop Direct) with £500 spend 2 months ago. Rule REJECTS case.",
  "rejection_message": "Recent spending detected on Creation/Sygma/Laser account",
  "is_creditor_specific": true,
  "applies_to_creditors": ["Creation", "Sygma", "Laser"],
  "references": [
    "TIG_Criteria.md - Creditor Specific Rules",
    "Excel Criteria/TIG_Criteria.md line 142"
  ],
  "related_rules": ["TIG-19", "TIG-19.1"],
  "last_reviewed": "2026-05-15",
  "review_notes": "Verified against Excel sheet - matches 3 & 4 month rule"
}
```

---

## Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| **Rules Documented** | 58/58 (100%) | After Phase 4 |
| **Frontend Load Time** | <200ms | After Phase 3 |
| **Detail View Load Time** | <100ms | After Phase 3 |
| **Search Coverage** | All fields | After Phase 3 |
| **Related Rules Links** | 100% working | After Phase 4 |
| **Review Coverage** | 100% dated | After Phase 4 |
| **API Response Time** | <50ms | After Phase 2 |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Data loss** | Backup DB before migration |
| **Performance degradation** | Add indexes on frequently searched columns |
| **Broken references** | Validate all JSON arrays during population |
| **Incomplete documentation** | Create checklist, manual review required |
| **Frontend complexity** | Use existing component patterns |

---

## Training & Documentation

**Post-Implementation:**
1. Admin User Guide: How to manage rules
2. API Documentation: New fields & parameters
3. Caseworker Guide: Understanding categories & related rules
4. Developer Guide: Database schema & API

---

## Estimated Effort

| Phase | Days | Effort |
|-------|------|--------|
| Schema & Migration | 2 | Backend dev |
| API Enhancement | 2 | Backend dev |
| Frontend Components | 4 | Frontend dev |
| Data Population | 3 | Scripts + Manual |
| QA & Testing | 3 | QA + Dev |
| Documentation | 1 | Technical writer |
| **TOTAL** | **15 days** | **~8 weeks (part-time)** |

---

## Next Steps

1. ✅ Review this plan with stakeholders
2. ⏭️ Approve database schema
3. ⏭️ Schedule Sprint Planning
4. ⏭️ Create GitHub issues/tickets
5. ⏭️ Assign team members
6. ⏭️ Begin Phase 1: Database Migration
7. ⏭️ Set up monitoring
8. ⏭️ Plan deployment strategy

---

**Document Generated:** May 22, 2026  
**Plan Status:** Ready for Implementation  
**Owner:** Development Team  
**Reviewer:** [To be assigned]
