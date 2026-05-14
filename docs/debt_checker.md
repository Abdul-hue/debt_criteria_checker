# Debt Criteria Checker — Implementation Fix Prompt

Paste this entire prompt to any AI (Claude, ChatGPT, etc.) followed by your project code.
The AI will implement all fixes against the confirmed rule knowledge base and the live JSON payload format.

---

## ROLE

You are a senior Django backend engineer working on a UK debt insolvency system called the **Debt Criteria Checker**. Your job is to implement and fix the `criteria_engine.py`, seed data, and model definitions so that the engine correctly evaluates a case against all 58 official rules.

---

## INPUT FORMAT — THE CASE ASSESSMENT JSON PAYLOAD

The debt checker receives a single JSON object from the upstream Case Assessment microservice. This is the **exact structure** you must parse:

```json
{
  "applicationId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "under_review",
  "phase": "assessment",

  "clientInfo": {
    "dateOfBirth": "1985-06-15"
  },

  "creditors": [
    {
      "id": "uuid",
      "creditor_name": "Barclays Bank",
      "account_reference": "123456789",
      "balance": "5400.00",
      "monthly_repayment": "150.00",
      "creditor_type": "unsecured_loan"
    }
  ],

  "gold_transactions": [
    {
      "id": "uuid",
      "description": "BARCLAYS LOAN REP",
      "amount": "150.00",
      "category": "Financial Liability",
      "transaction_type": "money_out",
      "signed_amount": -150.00,
      "source_doc_type": "bank_statement",
      "is_excluded": false
    }
  ],

  "mortgage_details": [
    {
      "lender_name": "Nationwide",
      "balance": "150000.00",
      "monthly_payment": "850.00",
      "is_joint": false
    }
  ],

  "financial_summary": {
    "total_income": 2500.00,
    "total_expenditure": 1800.00,
    "net_balance": 700.00,
    "income_source": "payslip",
    "documents": {
      "payslips": {},
      "bank_statements": {},
      "creditor_reports": {},
      "benefit_letters": {},
      "other": {}
    }
  },

  "evidence_ledger": [
    {
      "category": "debt",
      "source": "creditor_report",
      "value": 6650.50,
      "verified": true
    }
  ],

  "documents": [
    {
      "document_type": "bank_statement",
      "file_name": "bank_statement_jan.pdf",
      "extracted_data": {
        "is_valid": true,
        "account_holder": "John Doe",
        "statement_date": "2026-04-01",
        "transactions": []
      },
      "is_valid": true
    }
  ],

  "crm_data": {
    "crm_id": "CRM-98765",
    "total_unsecured_debt": 6650.50,
    "total_secured_debt": 150000.00
  },

  "has_property": true,
  "has_vehicle": false,
  "has_mortgage": true,
  "has_job": true,
  "has_uc_journal": false
}
```

### Field mapping rules — how to derive checker inputs from this JSON

| Criteria input needed | Where to get it from the JSON |
|---|---|
| `total_debt` | `crm_data.total_unsecured_debt` (primary); fallback: sum of `creditors[].balance` |
| `disposable_income` | `financial_summary.net_balance` |
| `available_equity` | Compute from mortgage if `has_property=true`: needs property value field (add if missing) |
| `months_to_repay` | `total_debt / disposable_income` — compute in engine |
| `creditor_list` | `creditors[]` array — each item has `creditor_name`, `balance`, `creditor_type` |
| `is_watch_creditor` | Look up `creditor_name` against `CreditorCriteria` where `representative="WATCH"` |
| `is_tix_creditor` | Look up against `representative="TIX"` |
| `is_evolve_creditor` | Look up against `representative="EVOLVE"` |
| `single_creditor_check` | Count creditors with `balance > 500` — if ≤ 1, trigger single_creditor block |
| `income_source` | `financial_summary.income_source` |
| `has_wage_slips` | Check `financial_summary.documents.payslips` is not empty AND check `documents[]` for `document_type="payslip"` with valid `extracted_data` |
| `wage_slip_date` | From `documents[]` where `document_type="payslip"` → `extracted_data.statement_date` |
| `has_bank_statement` | `documents[]` where `document_type="bank_statement"` and `is_valid=true` |
| `bank_statement_date` | `extracted_data.statement_date` on the bank statement doc |
| `bank_statement_account_holder` | `extracted_data.account_holder` on the bank statement doc |
| `has_uc_journal` | `has_uc_journal` boolean field |
| `gambling_amount_monthly` | Scan `gold_transactions[]` where `description` contains "GAMBLE", "BET", "CASINO", "PADDY", "LADBROKES", "BETFAIR", "WILLIAM HILL" etc. — sum `amount` |
| `recent_spend_creditors` | Scan `gold_transactions[]` for creditor-linked spending — flag if transaction date within 3 months |
| `vehicle_value` | Add `vehicle_value` field to payload (currently missing — note this gap) |
| `vehicle_hp_monthly` | Scan `gold_transactions[]` for HP/finance payments; or add explicit field |
| `client_age` | Compute from `clientInfo.dateOfBirth` |
| `children_ages` | Add `children` array to payload (currently missing — note this gap) |
| `previous_iva` | Check `evidence_ledger[]` or add explicit boolean field |
| `antecedent_transactions` | Add explicit boolean field to payload (currently missing — note this gap) |
| `shop_direct_spend_date` | Scan `gold_transactions[]` for Shop Direct / Very / Littlewoods descriptions |
| `creation_spend_date` | Scan `gold_transactions[]` for Creation / Sygma / Laser descriptions |
| `car_finance_date` | Scan `gold_transactions[]` where `creditor_type="car_finance"` or description matches |

---

## COMPLETE RULE KNOWLEDGE BASE — SOURCE OF TRUTH

Implement every rule below exactly as specified. Do not invent thresholds. Do not add rules not listed here.

### TIG rules — run for ALL cases

| Rule ID | Severity | Logic |
|---|---|---|
| TIG-01 | hard_block | `total_debt < 6000` → block |
| TIG-02 | hard_block | `disposable_income <= 100` → block |
| TIG-03 | flag → hard_block | expense exceeds SFS guideline → flag; if unjustified → block |
| TIG-04 | hard_block | `DLA + PIP > 0` AND `disability_expenses == 0` → block |
| TIG-05 | hard_block | 1 wage slip per employment income source required, dated within 3 months; missing or outdated → block |
| TIG-06 | hard_block | benefit income exists but no award letter or current-year bank statement → block |
| TIG-07 | hard_block | UC income exists but `has_uc_journal=false` OR journal older than 3 months → block |
| TIG-08 | hard_block | self-employed but no tax return AND no 3-month business banking; or newly self-employed under 3 months → block |
| TIG-09 | hard_block | CIS income exists but no CIS invoice showing 20% tax deduction → block |
| TIG-10 | hard_block | debt recorded with no supporting proof → block; exception: debts under £1,000 may be verbal → flag only if it does not affect minimum debt level |
| TIG-11 | hard_block + flag | No bank statement, or statement older than 3 months, or no account_holder name → hard_block. Gambling > £1,000/month → hard_block. Gambling > £200/month → flag + require GAMSTOP proof. Unexplained DDs/SOs → flag |
| TIG-12 | hard_block | third-party contribution exists but no signed letter (must include name, address, signature, date, contact, amount, duration) → block |
| TIG-13 | hard_block | previous IVA on record but no termination report uploaded → block |
| TIG-15.1 | hard_block | HMRC is majority creditor AND income/benefit deductions already being taken → block |
| TIG-15.2 | hard_block | HMRC is majority creditor AND client has previous IVA or bankruptcy → block |
| TIG-15.3 | hard_block | HMRC self-assessment debt + still self-employed + late or missing tax submissions → block |
| TIG-15.4 | hard_block | available property equity > HMRC debt balance → block |
| TIG-15.5 | hard_block | bankruptcy return > IVA payments → block |
| TIG-15.6 | hard_block | Full & Final funded from savings accumulated while debts unpaid → block |
| TIG-15.7 | hard_block | incorrectly claimed SEISS debt → always block; cannot be included in IVA |
| TIG-15.8 | info | HMRC removes client name, chases other party → does NOT block |
| TIG-15.9 | info | HMRC debt < £4,000 → HMRC will not vote unless rejecting; does NOT block |
| TIG-15.10 | hard_block | client's only income is benefits AND HMRC is a creditor → block |
| TIG-16 | flag | NON-WPM or EVERSHEDS cases only; equity > total debt → flag; assessor must explain why not remortgaging |
| TIG-17 | flag | council is majority creditor AND income/benefit deductions being taken → flag; case-by-case review |
| TIG-18 | flag | total spend in last 2 months ≥ monthly income (excluding payday loans) → flag for human review; NOT a block |
| TIG-19 | flag | Shop Direct: purchases within 3 months of statement date OR 4 months of order date → flag |
| TIG-19.1 | hard_block | Shop Direct account < 6 months old → hard block regardless of spend |
| TIG-20 | flag | Creation: purchases within 3 months of statement date or 4 months of order date → flag |
| TIG-20.1 | hard_block | any recent spend with Creation, Sygma, or Laser → hard block (no trial cases) |
| TIG-21.1 | flag | Link Financial is a creditor → must confirm Mid SFS guidelines used |
| TIG-21.2 | hard_block | `total_debt < 12000` AND Link Financial is a creditor → block |
| TIG-21.3 | hard_block | property equity > Link Financial debt balance → block |
| TIG-21.4 | hard_block | benefits > 10% of household income AND Link Financial is a creditor → block |
| TIG-21.5 | hard_block | previous IVA failed due to arrears AND Link Financial is a creditor → block |

### WATCH rules — run ONLY when WATCH is a creditor

| Rule ID | Severity | Logic |
|---|---|---|
| WATCH-22.1 | flag | vulnerability used to justify exception but no supporting document uploaded → flag |
| WATCH-22.2 | hard_block | `months_to_repay = total_debt / disposable_income`; if `months_to_repay <= 72` → block |
| WATCH-22.3 | hard_block | bankruptcy return > IVA return → block |
| WATCH-22.4 | hard_block | available equity > total unsecured debt → block |
| WATCH-22.5 | hard_block | only 1 creditor, OR second creditor balance ≤ £500 → block |
| WATCH-22.6 | hard_block | any spending on any account within the last 3 months → block |
| WATCH-22.7 | flag | client has children aged 13 or above AND no sustainability paragraph in IVA proposal → flag |
| WATCH-22.8 | info | client aged 80 or above → WATCH will abstain; does NOT block |
| WATCH-22.9 | flag | vehicle value > £9,000 → flag; WATCH may request reduction to £4,500 |
| WATCH-22.10 | flag | car HP payment > £400/month → flag; requires evidence |
| WATCH-22.11 | flag | gambling identified as main cause AND no 3-month clean bank statements → flag |
| WATCH-22.12 | flag | IVA previously proposed; I&E/assets/liabilities must be consistent OR written explanation → flag |
| WATCH-22.13 | hard_block | antecedent transactions identified → block; no exceptions |
| WATCH-22.14 | hard_block | car finance taken in last 3 months → block; unless valid evidence (old car scrapped, accident, employment) |

### TIX rules — run ONLY when TIX is a creditor

| Rule ID | Severity | Logic |
|---|---|---|
| TIX-01 | hard_block | Shop Direct / Very / Littlewoods: spend in last 3 months → block |
| TIX-02 | hard_block | Shop Direct account < 6 months old → block |
| TIX-03 | hard_block | Creation / Sygma / Laser: spend in last 4 months → block |
| TIX-04 | flag | car HP payment > £250/month → flag — NOTE: TIX threshold is £250, WATCH is £400 |
| TIX-05 | info | UKAR, Whistletree, Computershare, Landmark no longer represented by TIX after 30 June 2023 |
| TIX-06 | flag | vulnerability used without supporting document → flag |

### EVOLVE rules — run ONLY when EVOLVE is a creditor

| Rule ID | Severity | Logic |
|---|---|---|
| EVOLVE-01 | hard_block | equity > debt based on 85% LTV (not 100%) → block |
| EVOLVE-02 | hard_block | only 1 creditor (NatWest loan + credit card + overdraft + bounce-back = ONE lender) → block if no separate lender with > £500 |
| EVOLVE-03 | flag | vulnerability used without supporting document → flag |

---

## CONFIRMED BUGS TO FIX

These are verified errors in the existing implementation. Fix all of them:

| Bug | Current (wrong) | Correct |
|---|---|---|
| TIG-01 threshold | 5000 | 6000 |
| TIG-02 threshold | 50 | 100 |
| WATCH-22.5 severity | flag | hard_block |
| TIG-20 severity | hard_block | flag (TIG-20.1 is the block, not TIG-20) |
| `majority_threshold` 75% rule | hard_block | DELETE — phantom rule, not in source documents |
| `parent_group_conflict` | GlobalCriteria rule | Move to seeded CreditorCriteria data — it is a data lookup, not a rule |
| `is_watch` / `is_tix` / `is_evolve` BooleanFields | exist alongside `representative` | Remove — use `representative` CharField only |
| WATCH HP threshold | not set | 400 |
| TIX HP threshold | not set | 250 — different from WATCH |
| TIG-04 label | TIG-03 | TIG-04 |
| TIG-05 label | TIG-04 | TIG-05; also add "1 per income source" check |
| TIG-10 label | TIG-12 | TIG-10 |
| TIG-11 label | TIG-09 | TIG-11; add account_holder name check and DD/SO flag |

---

## BANKING GROUPS — seed as CreditorCriteria data

| Group name | Members |
|---|---|
| RBS Group | Royal Bank of Scotland, NatWest, Ulster Bank, Coutts, Think Banking |
| Lloyds Group | Lloyds, Bank of Scotland, Halifax, Blackhorse, Birmingham Midshires, AA, Intelligent Finance, Cheltenham & Gloucester, Saga |
| Barclays Group | Barclays, Barclays Direct, Barclaycard, Woolwich, Standard Life |
| HSBC Group | HSBC, First Direct, Midland Bank |
| Santander Group | Santander, Cahoot, Alliance & Leicester, Abbey National |
| Co-op Group | Co-operative Bank, Smile, Britannia Building Society |
| Bank of Ireland Group | Bank of Ireland, Post Office |
| Nationwide Group | Nationwide, Cheshire BS, Derbyshire BS, Dunfermline BS |
| Yorkshire BS Group | Yorkshire BS, Barnsley BS, Chelsea BS, Norwich & Peterborough BS |
| Clydesdale Group | Clydesdale Bank, Yorkshire Bank, National Australia |
| Skipton Group | Skipton BS, Chesham BS, Scarborough BS |
| Coventry Group | Coventry BS, Stroud & Swindon BS |

Shop Direct group trading names: **Shop Direct**, **Very**, **Littlewoods**, **Littlewoods.com** — treat as same creditor for all rule checks.

---

## IMPLEMENTATION INSTRUCTIONS

When I paste code, implement the following in order:

### Step 1 — Fix the criteria_engine.py

For each rule above, implement a method `_rule_{rule_id_snake}(self, case)` that:
1. Receives the parsed case dict (from the JSON above)
2. Derives all needed values using the **field mapping table** in this prompt
3. Returns a `RuleResult` with: `rule_id`, `severity` (hard_block / flag / info / pass), `triggered` (bool), `message` (human-readable reason)

Each rule method must be **independent** — no shared mutable state between rules.

The engine must have a main `evaluate(case_json)` method that:
1. Always runs all TIG rules
2. Detects if WATCH/TIX/EVOLVE is a creditor by looking up `creditors[].creditor_name` against `CreditorCriteria` table
3. Runs WATCH/TIX/EVOLVE rules only if that representative is present
4. Returns a structured result: `{ "hard_blocks": [...], "flags": [...], "info": [...], "overall": "blocked" | "flagged" | "pass" }`

### Step 2 — Fix the seed data

- Delete the `majority_threshold` rule
- Fix TIG-01 `threshold_value` to `6000`
- Fix TIG-02 `threshold_value` to `100`
- Fix WATCH-22.5 `severity` to `hard_block`
- Fix TIG-20 `severity` to `flag`
- Set WATCH-22.10 `threshold_value` to `400`
- Add TIX-04 with `threshold_value` of `250`
- Add all missing rules as seed entries with correct severities and thresholds

### Step 3 — Fix the models

- Remove `is_watch`, `is_tix`, `is_evolve` BooleanFields from `CreditorCriteria` if they exist alongside `representative`
- Move `parent_group_conflict` logic out of `GlobalCriteria` and into `CreditorCriteria` seeded data
- Seed all 12 banking groups into `CreditorCriteria.parent_group`

### Step 4 — Gap fields (note in code with TODO)

The current JSON payload is missing these fields needed for full rule coverage. Add `TODO` comments where they are needed and write defensive code that returns `flag` (not hard_block) when data is absent:
- `vehicle_value` — needed for WATCH-22.9
- `children` array with ages — needed for WATCH-22.7
- `antecedent_transactions` boolean — needed for WATCH-22.13
- `property_value` — needed to compute equity for WATCH-22.4, EVOLVE-01, TIG-15.4
- `car_finance_date` — needed for WATCH-22.14
- `sustainability_paragraph_present` — needed for WATCH-22.7
- `third_party_contribution` details — needed for TIG-12
- `seiss_debt_flag` — needed for TIG-15.7

---

## OUTPUT FORMAT FOR EACH RULE RESULT

```python
@dataclass
class RuleResult:
    rule_id: str          # e.g. "TIG-01"
    severity: str         # "hard_block" | "flag" | "info" | "pass"
    triggered: bool       # True if rule fired
    message: str          # Human-readable explanation
    threshold: float | None = None   # The threshold that was compared, if applicable
    actual_value: float | None = None  # The actual value from the case
```

---

## RULES FOR THE AI IMPLEMENTING THIS

1. Never invent a rule not listed in this prompt. If you are unsure whether something is a rule, do not add it.
2. Never change a severity — if the table says `flag`, implement `flag` even if `hard_block` seems more intuitive.
3. The TIX HP threshold is £250. The WATCH HP threshold is £400. They are different. Do not merge them.
4. `majority_threshold` at 75% does NOT exist. Delete it if you see it.
5. Parse `balance` fields as `Decimal` or `float` — they arrive as strings in the JSON.
6. When a required field is missing from the JSON, default to the safest non-blocking behaviour (flag, not hard_block) and include a note in the message.
7. Keep each rule method under 30 lines. If it is longer, extract a helper.
8. Write a unit test for every rule that has a threshold — test the value at threshold, one below, and one above.

---

*Paste your implementation code below this line.*