# Payload Contract — Debt Criteria Assessment Engine

**Endpoint:** `POST /api/v1/assess/`  
**Content-Type:** `application/json`  
**Auth:** None (service-to-service; restrict by network/IP in production)  
**Engine version:** 58 rules (TIG, WATCH, TIX, EVOLVE)

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Engine fully evaluates this field today |
| ⚠️ | Engine reads this field but evaluation is partial |
| 🔴 | Field missing → rules that depend on it return `_todo_flag` (not evaluated) |

---

## Top-Level Structure

```json
{
  "application_id":            "string",
  "case_type":                 "string",
  "proposed_dividend_pence":   "integer",
  "override_code":             "string | null",
  "override_reason":           "string | null",
  "override_by":               "string | null",
  "clientInfo":                { ... },
  "financial_summary":         { ... },
  "crm_data":                  { ... },
  "creditors":                 [ ... ],
  "evidence_ledger":           [ ... ],
  "documents":                 [ ... ],
  "gold_transactions":         [ ... ],
  "mortgage_details":          [ ... ],
  "property_value":            "decimal | null",
  "vehicle_value":             "decimal | null",
  "children":                  [ ... ],
  "antecedent_transactions":   "boolean | array | null",
  "seiss_debt_flag":           "boolean",
  "third_party_contribution":  "decimal | null",
  "sustainability_paragraph_present": "boolean",
  "bankruptcy_return":         "decimal | null",
  "vulnerability_claimed":     "boolean",
  "income_deductions_active":  "boolean",
  "full_and_final_from_savings": "boolean",
  "benefit_income_breakdown":  [ ... ],
  "disability_income":         "decimal | null",
  "disability_expenses":       "decimal | null",
  "sfs_expenditure_breakdown": [ ... ]
}
```

---

## Field Reference

### Case Metadata

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `application_id` | string | Yes | ✅ | Aryza/HubSolv case reference. Stored on `CriteriaDecision`. |
| `case_type` | string | No | ✅ | e.g. `"IVA"`, `"DMP"`. Defaults to `""` if absent. |
| `proposed_dividend_pence` | integer | No | ✅ | Pence per pound proposed to creditors. e.g. `30` = 30p/£1. |
| `override_code` | string | No | ✅ | Must be one of `MANAGER_REVIEW`, `COMPLIANCE_SIGN_OFF`, `SENIOR_CASEWORKER`. Demotes hard blocks to flags when valid. |
| `override_reason` | string | No | ✅ | Required alongside `override_code` for override to apply. |
| `override_by` | string | No | ✅ | Username/ID of person authorising override. Required alongside `override_code`. |

---

### `clientInfo` Object

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `clientInfo.full_name` | string | No | ✅ | Client display name. |
| `clientInfo.date_of_birth` | string (ISO date) | No | ✅ | `"YYYY-MM-DD"`. Alias of `dateOfBirth`; engine accepts either for age. |
| `clientInfo.dateOfBirth` | string (ISO date) | No | ✅ | Same as `date_of_birth` (camelCase). |
| `clientInfo.employment_status` | string | No | ✅ | e.g. `"employed"`, `"self_employed"`, `"benefits_only"`, `"unemployed"`. |
| `clientInfo.previous_iva` | boolean | No | ✅ | Whether client has had a previous IVA. |
| `clientInfo.previous_iva_failed_reason` | string | No | ⚠️ | Used as proxy where available. No dedicated rule yet. |

---

### `financial_summary` Object

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `financial_summary.net_balance` | decimal | Yes | ✅ | Monthly disposable income (income minus expenses). Core to multiple TIG rules. |
| `financial_summary.total_income` | decimal | Yes | ✅ | Total gross monthly income. |
| `financial_summary.total_expenses` | decimal | No | ✅ | Total monthly expenditure. |
| `financial_summary.income_source` | string | No | ✅ | Primary income source label. e.g. `"salary"`, `"universal_credit"`, `"benefits"`. |
| `financial_summary.savings_contribution` | decimal | No | ✅ | Monthly IVA contribution figure. |

---

### `crm_data` Object

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `crm_data.total_unsecured_debt` | decimal | No | ✅ | Overrides summed creditor balances if present. |
| `crm_data.gambling_main_cause` | boolean | No | ✅ | Whether gambling is the primary cause of debt. Feeds WATCH-22.12. |
| `crm_data.crm_bank_name` | string | No | ✅ | Primary bank name from CRM. |

---

### `creditors` Array

Each element represents one creditor/debt line.

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `creditor_name` | string | Yes | ✅ | Raw creditor name as entered. Matched against `CreditorCriteria` trading names. |
| `balance` | decimal | Yes | ✅ | Outstanding balance in GBP. |
| `creditor_type` | string | No | ✅ | e.g. `"credit_card"`, `"loan"`, `"hmrc_paye"`, `"council_tax"`. |
| `representative` | string | No | ✅ | `WATCH`, `TIX`, `EVOLVE`, or `NONE`. Overrides DB lookup if provided. |
| `parent_group` | string | No | ✅ | Banking group. e.g. `"Lloyds Banking Group"`. Used for conflict checking. |
| `min_dividend_pence` | integer | No | ✅ | Minimum pence per pound this creditor accepts. |
| `account_age_months` | integer | No | ✅ | Age of account in months. Used for Shop Direct rules. |
| `last_transaction_date` | string (ISO date) | No | ✅ | `"YYYY-MM-DD"`. Used for dormancy rules. |
| `linked_creditor` | string | No | ✅ | Reference matching an `evidence_ledger[].ref`. Used by TIG-10 proof-of-debt check. |
| `covers_months` | integer | No | ✅ | Number of months the creditor statement covers. |
| `has_ccj` | boolean | No | ✅ | Whether a County Court Judgement exists for this debt. Used by TIG-10. |

**Example:**
```json
{
  "creditor_name": "Lloyds Bank",
  "balance": 8500.00,
  "creditor_type": "loan",
  "representative": "NONE",
  "parent_group": "Lloyds Banking Group",
  "min_dividend_pence": 25,
  "account_age_months": 36,
  "last_transaction_date": "2024-11-01",
  "linked_creditor": "EVID-003",
  "covers_months": 3,
  "has_ccj": false
}
```

---

### `evidence_ledger` Array

Links uploaded documents to specific creditors. Required for TIG-10 proof-of-debt evaluation.

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `ref` | string | Yes | ✅ | Unique reference. Must match `creditors[].linked_creditor`. |
| `doc_type` | string | No | ✅ | e.g. `"bank_statement"`, `"creditor_statement"`, `"ccj"`, `"court_order"`. |
| `description` | string | No | ✅ | Free-text description. |

**Example:**
```json
{ "ref": "EVID-003", "doc_type": "creditor_statement", "description": "Lloyds loan statement" }
```

---

### `documents` Array

Case-level documents uploaded by the advisor.

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `document_type` | string | No | ✅ | e.g. `"wage_slip"`, `"bank_statement"`, `"ccj_document"`, `"gambling_clean_statement"`. |
| `covers_months` | integer | No | ✅ | Number of months this document covers. |
| `linked_creditor` | string | No | ✅ | Creditor name this document relates to. |

---

### `gold_transactions` Array

Bank transaction records (AI-categorised).

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `description` | string | No | ✅ | Transaction description. |
| `amount` | decimal | No | ✅ | Transaction amount. |
| `category` | string | No | ✅ | AI-assigned category. e.g. `"gambling"`, `"luxury"`. |
| `transaction_type` | string | No | ✅ | `"debit"` or `"credit"`. |
| `flagged` | boolean | No | ✅ | Whether transaction was flagged for review. |

---

### `mortgage_details` Array

| Field | Type | Required | Status | Notes |
|-------|------|----------|--------|-------|
| `balance` | decimal | No | ✅ | Per-row balance; preferred when both `balance` and `outstanding_balance` are present. |
| `outstanding_balance` | decimal | No | ✅ | Used when `balance` is absent. Engine sums **one amount per row** (`balance` else `outstanding_balance`). |
| `monthly_payment` | decimal | No | ✅ | Monthly mortgage payment. |
| `lender` | string | No | ✅ | Mortgage lender name. |

---

## Fields Required to Unblock Stubbed Rules

`_parse_case` copies **Group D** items, **`vulnerability_claimed`**, and **mortgage** normalisation onto the rule dict **`c`** when present in JSON (see `docs/ARCHITECTURE.md` §11.1). Remaining rows below are still needed where rules depend on them; missing keys continue to yield `_todo_flag` or skipped checks until supplied.

### Group A — Property (unblocks TIG-15.4, TIG-16, TIG-21.3, WATCH-22.4, EVOLVE-01)

| Field | Type | Where in payload | Notes |
|-------|------|-----------------|-------|
| `property_value` | decimal | top-level | Estimated current market value. |
| `mortgage_outstanding` | decimal | top-level (optional) | If omitted, engine **derives** total from `mortgage_details` (per-row `balance` or `outstanding_balance`). |

### Group B — Conduct / Legal (unblocks WATCH-22.13, TIG-15.5, TIG-15.7, TIG-15.6)

| Field | Type | Where in payload | Notes |
|-------|------|-----------------|-------|
| `antecedent_transactions` | boolean | top-level | True if advisor has identified antecedent transactions. Hard block, no exceptions. |
| `bankruptcy_return` | decimal | top-level | Estimated annual return in bankruptcy scenario. |
| `seiss_debt_flag` | boolean | top-level | True if SEISS grant debt is included. |
| `full_and_final_from_savings` | boolean | top-level | True if F&F offer is funded from savings accumulated while debts unpaid. |

### Group C — Vulnerability / Client (unblocks WATCH-22.1, TIX-06, EVOLVE-03, WATCH-22.7, TIG-12)

| Field | Type | Where in payload | Notes |
|-------|------|-----------------|-------|
| `vulnerability_claimed` | boolean | top-level | True if client has declared a vulnerability. |
| `children` | array | top-level | Array of `{ "age": integer }`. Used for WATCH-22.7 (children 13+). |
| `third_party_contribution` | decimal | top-level | Monthly amount contributed by a third party. |
| `sustainability_paragraph_present` | boolean | top-level | True if proposal includes a sustainability paragraph. |

### Group D — Income / Expenditure (unblocks TIG-03, TIG-04, TIG-15.1, TIG-21.4)

| Field | Type | Where in payload | Notes |
|-------|------|-----------------|-------|
| `sfs_expenditure_breakdown` | array | top-level | Array of `{ "category": string, "monthly_amount": decimal, "sfs_guideline_max": decimal }`. |
| `disability_income` | decimal | top-level | Monthly income from DLA/PIP. |
| `disability_expenses` | decimal | top-level | Monthly disability-related expenditure. |
| `income_deductions_active` | boolean | top-level | True if Attachment of Earnings or similar deduction is active. |
| `benefit_income_breakdown` | array | top-level | Array of `{ "type": string, "monthly_amount": decimal }`. Types: `universal_credit`, `dla`, `pip`, `tax_credits`, `other`. |
| `vehicle_value` | decimal | top-level | Estimated vehicle value. Used for WATCH-22.9. |

---

## Response Structure

```json
{
  "overall": "pass | flagged | indeterminate | blocked",
  "is_indeterminate": "boolean",
  "override_applied": "boolean",
  "override_meta": {
    "code": "string",
    "reason": "string",
    "by": "string"
  },
  "representatives_detected": ["WATCH", "TIX"],
  "summary": {
    "hard_block_count": "integer",
    "flag_count": "integer",
    "info_count": "integer",
    "passed_count": "integer"
  },
  "hard_blocks": [ "RuleResult[]" ],
  "flags":       [ "RuleResult[]" ],
  "info":        [ "RuleResult[]" ],
  "passed":      [ "RuleResult[]" ],
  "advisory_notes": [ "string" ]
}
```

### `RuleResult` Object

```json
{
  "rule_id":        "TIG-01",
  "severity":       "hard_block | flag | info | pass",
  "triggered":      "boolean",
  "message":        "string",
  "threshold":      "decimal | null",
  "actual_value":   "decimal | null",
  "overridden":     "boolean",
  "override_code":  "string | null",
  "override_reason":"string | null",
  "override_by":    "string | null"
}
```

### `overall` Values

| Value | Meaning |
|-------|---------|
| `pass` | No hard blocks, no flags. Case is clean. |
| `flagged` | No hard blocks but one or more flags raised. Caseworker review needed. |
| `indeterminate` | Flags present that cannot be auto-resolved (TIG-10, TIG-07, WATCH-22.1). Human decision required. |
| `blocked` | One or more hard blocks. Case cannot proceed as-is. |

---

## Minimal Valid Payload (for testing)

```json
{
  "application_id": "TEST-001",
  "case_type": "IVA",
  "proposed_dividend_pence": 30,
  "financial_summary": {
    "net_balance": 200.00,
    "total_income": 2500.00,
    "total_expenses": 2300.00,
    "income_source": "salary"
  },
  "crm_data": {
    "total_unsecured_debt": 18000.00,
    "gambling_main_cause": false
  },
  "creditors": [
    {
      "creditor_name": "Lloyds Bank",
      "balance": 10000.00,
      "creditor_type": "loan",
      "linked_creditor": "EVID-001",
      "covers_months": 3,
      "has_ccj": false
    },
    {
      "creditor_name": "Barclays",
      "balance": 8000.00,
      "creditor_type": "credit_card",
      "linked_creditor": "EVID-002",
      "covers_months": 3,
      "has_ccj": false
    }
  ],
  "evidence_ledger": [
    { "ref": "EVID-001", "doc_type": "creditor_statement" },
    { "ref": "EVID-002", "doc_type": "creditor_statement" }
  ],
  "documents": [],
  "gold_transactions": [],
  "mortgage_details": []
}
```

---

## Stub Rules Reference

Rules currently returning `_todo_flag` — they will evaluate once the
corresponding payload field is present. No engine code changes are needed.

| Rule | Missing Field | Severity | Impact if Untreated |
|------|--------------|----------|---------------------|
| TIG-03 | `sfs_expenditure_breakdown` | flag | Expenditure SFS check skipped |
| TIG-04 | `disability_income / disability_expenses` | flag | Disability cost check skipped |
| TIG-12 | `third_party_contribution` | flag | Third-party letter check skipped |
| TIG-15.1 | `income_deductions_active` | flag | Deductions check skipped |
| TIG-15.4 | `property_value` | **hard_block** | ⚠️ Equity rule not enforced |
| TIG-15.5 | `bankruptcy_return` | flag | Bankruptcy comparison skipped |
| TIG-15.6 | `full_and_final_from_savings` | flag | F&F savings check skipped |
| TIG-15.7 | `seiss_debt_flag` | flag | SEISS check skipped |
| TIG-16 | `property_value` | **hard_block** | ⚠️ Equity rule not enforced |
| TIG-21.3 | `property_value` | **hard_block** | ⚠️ Equity rule not enforced |
| TIG-21.4 | `benefit_income_breakdown` | flag | Mixed income check skipped |
| WATCH-22.1 | `vulnerability_claimed` | flag | Vulnerability check skipped |
| WATCH-22.3 | `bankruptcy_return` | flag | Bankruptcy comparison skipped |
| WATCH-22.4 | `property_value` | **hard_block** | ⚠️ Equity rule not enforced (WATCH) |
| WATCH-22.7 | `children` | flag | Children sustainability check skipped |
| WATCH-22.9 | `vehicle_value` | flag | Vehicle asset check skipped |
| WATCH-22.13 | `antecedent_transactions` | **hard_block** | ⚠️ Fraud signal not enforced |
| TIX-06 | `vulnerability_claimed` | flag | Vulnerability check skipped (TIX) |
| EVOLVE-01 | `property_value` | **hard_block** | ⚠️ Equity rule not enforced (EVOLVE) |
| EVOLVE-03 | `vulnerability_claimed` | flag | Vulnerability check skipped (EVOLVE) |

**⚠️ 6 hard_block rules are not currently enforcing** when the request body omits the needed fields. Case Assessment can send Group A/B data; cases that should be blocked may pass through **if those fields are missing on the assess POST** for that case.