# Debt Criteria Checker — Implementation Plan

## How to use this file

Work through each phase in order. Do not start Phase 2 until Phase 1 is complete and verified.
After completing each task, mark it `[x]`. If a task is blocked, mark it `[!]` and note why.
Each phase is designed to be a single Opus session. Paste only the files relevant to that phase.

---

## Context for the AI in every session

Before starting any phase, paste this block at the top of your message:

> "You are implementing fixes to a Django debt criteria checker. The system receives a JSON payload
> from a case assessment microservice and evaluates it against 58 official IVA eligibility rules.
> Work through the tasks in this plan one at a time. After each task, confirm what you did before
> moving to the next. Do not invent rules. Do not change severities. Follow the plan exactly."

---

## Phase 1 — Models and structure
**Files needed:** `models.py`
**Goal:** Clean up the data model before any logic changes. No rule logic in this phase.

### Tasks

- [ ] **P1-T1** Remove `is_watch`, `is_tix`, `is_evolve` BooleanFields from `CreditorCriteria`
  - These are redundant with the existing `representative` CharField
  - After removal, confirm `representative` accepts values: `"WATCH"`, `"TIX"`, `"EVOLVE"`, `null`
  - Write a migration for this change

- [ ] **P1-T2** Remove `parent_group_conflict` from `GlobalCriteria` rules table
  - This is not a rule — it is a data attribute
  - It belongs as `parent_group` data on `CreditorCriteria` records
  - Confirm `CreditorCriteria` has a `parent_group` CharField (add if missing)

- [ ] **P1-T3** Add missing fields to `CreditorCriteria` if not present
  - `account_age_months` IntegerField (nullable) — for Shop Direct account age rules
  - `parent_group` CharField (nullable) — for banking group conflict detection

- [ ] **P1-T4** Confirm `RuleResult` dataclass exists (create in `criteria_engine.py` if not)
  ```python
  @dataclass
  class RuleResult:
      rule_id: str
      severity: str        # "hard_block" | "flag" | "info" | "pass"
      triggered: bool
      message: str
      threshold: float | None = None
      actual_value: float | None = None
  ```

- [ ] **P1-T5** Write and run migration
  - `python manage.py makemigrations`
  - `python manage.py migrate`
  - Confirm no existing data is lost

**Phase 1 verification:** Run `python manage.py check` — zero errors expected.

---

## Phase 2 — Seed data
**Files needed:** `seed_criteria_rules.py` (or equivalent management command)
**Goal:** Fix all wrong seed values and add every missing rule entry. No engine logic in this phase.

### Tasks — fix existing seeds

- [ ] **P2-T1** Delete `majority_threshold` rule entry entirely
  - This rule does not exist in any source document
  - It must not appear anywhere in the database or fixtures

- [ ] **P2-T2** Fix `TIG-01` (minimum debt)
  - `threshold_value` → `6000` (currently wrong: 5000)
  - `severity` → `hard_block`

- [ ] **P2-T3** Fix `TIG-02` (minimum disposable income)
  - `threshold_value` → `100` (currently wrong: 50)
  - `severity` → `hard_block`

- [ ] **P2-T4** Fix `WATCH-22.5` (single creditor)
  - `severity` → `hard_block` (currently wrong: flag)

- [ ] **P2-T5** Fix `TIG-20` (Creation recent spending)
  - `severity` → `flag` (currently wrong: hard_block)
  - Note: TIG-20.1 is the hard_block — TIG-20 itself is only a flag

- [ ] **P2-T6** Set `WATCH-22.10` HP threshold
  - `threshold_value` → `400`

### Tasks — add missing rule seeds

- [ ] **P2-T7** Add TIG rules that are entirely missing:
  - TIG-03 — SFS guidelines — severity: `flag`
  - TIG-04 — DLA/PIP offset — severity: `hard_block`
  - TIG-05 — wage slip required — severity: `hard_block`
  - TIG-06 — benefit income proof — severity: `hard_block`
  - TIG-07 — UC journal — severity: `hard_block`
  - TIG-08 — self-employed proof — severity: `hard_block`
  - TIG-09 — CIS income proof — severity: `hard_block`
  - TIG-10 — proof of debt — severity: `hard_block`
  - TIG-11 — bank statement verification — severity: `hard_block`
  - TIG-12 — third-party contribution — severity: `hard_block`
  - TIG-13 — previous IVA termination — severity: `hard_block`

- [ ] **P2-T8** Add all HMRC sub-rules:
  - TIG-15.1 — income deductions — `hard_block`
  - TIG-15.2 — previous IVA/bankruptcy — `hard_block`
  - TIG-15.3 — late tax submissions — `hard_block`
  - TIG-15.4 — equity > HMRC debt — `hard_block`
  - TIG-15.5 — bankruptcy return higher — `hard_block`
  - TIG-15.6 — full and final from savings — `hard_block`
  - TIG-15.7 — SEISS fraud debt — `hard_block`
  - TIG-15.8 — HMRC joint debt — `info`
  - TIG-15.9 — HMRC debt < £4,000 — `info`
  - TIG-15.10 — benefits-only income — `hard_block`

- [ ] **P2-T9** Add remaining TIG rules:
  - TIG-16 — equity exceeds liabilities — `flag`
  - TIG-17 — council majority deduction — `flag`
  - TIG-18 — recent spending review — `flag`
  - TIG-19 — Shop Direct recent spend — `flag`
  - TIG-19.1 — Shop Direct account age — `hard_block`
  - TIG-20.1 — Creation/Sygma/Laser hard block — `hard_block`
  - TIG-21.1 — Link Financial Mid SFS — `flag`
  - TIG-21.2 — Link Financial min debt, threshold: 12000 — `hard_block`
  - TIG-21.3 — Link Financial equity — `hard_block`
  - TIG-21.4 — Link Financial benefits — `hard_block`
  - TIG-21.5 — Link Financial previous IVA arrears — `hard_block`

- [ ] **P2-T10** Add all WATCH rule seeds (if missing):
  - WATCH-22.1 — vulnerability evidence — `flag`
  - WATCH-22.2 — debt repayable in 6 years, threshold: 72 months — `hard_block`
  - WATCH-22.3 — bankruptcy dividend higher — `hard_block`
  - WATCH-22.4 — equity greater than debt — `hard_block`
  - WATCH-22.6 — recent spending 3 months — `hard_block`
  - WATCH-22.7 — children over 13 — `flag`
  - WATCH-22.8 — client age 80+ — `info`
  - WATCH-22.9 — vehicle value > £9,000 — `flag`
  - WATCH-22.11 — gambling main cause — `flag`
  - WATCH-22.12 — previously proposed IVA — `flag`
  - WATCH-22.13 — antecedent transactions — `hard_block`
  - WATCH-22.14 — car finance in last 3 months — `hard_block`

- [ ] **P2-T11** Add all TIX rule seeds:
  - TIX-01 — Shop Direct recent spend — `hard_block`
  - TIX-02 — Shop Direct account age — `hard_block`
  - TIX-03 — Creation/Sygma/Laser — `hard_block`
  - TIX-04 — vehicle HP > £250/month, threshold: **250** — `flag`
  - TIX-05 — deregistered creditors — `info`
  - TIX-06 — vulnerability evidence — `flag`

- [ ] **P2-T12** Add all EVOLVE rule seeds:
  - EVOLVE-01 — equity greater than debt (85% LTV) — `hard_block`
  - EVOLVE-02 — single creditor — `hard_block`
  - EVOLVE-03 — vulnerability evidence — `flag`

- [ ] **P2-T13** Seed all 12 banking groups into `CreditorCriteria.parent_group`:
  ```
  RBS Group:       Royal Bank of Scotland, NatWest, Ulster Bank, Coutts, Think Banking
  Lloyds Group:    Lloyds, Bank of Scotland, Halifax, Blackhorse, Birmingham Midshires,
                   AA, Intelligent Finance, Cheltenham & Gloucester, Saga
  Barclays Group:  Barclays, Barclays Direct, Barclaycard, Woolwich, Standard Life
  HSBC Group:      HSBC, First Direct, Midland Bank
  Santander Group: Santander, Cahoot, Alliance & Leicester, Abbey National
  Co-op Group:     Co-operative Bank, Smile, Britannia Building Society
  BoI Group:       Bank of Ireland, Post Office
  Nationwide Group:Nationwide, Cheshire BS, Derbyshire BS, Dunfermline BS
  Yorkshire Group: Yorkshire BS, Barnsley BS, Chelsea BS, Norwich & Peterborough BS
  Clydesdale Group:Clydesdale Bank, Yorkshire Bank, National Australia
  Skipton Group:   Skipton BS, Chesham BS, Scarborough BS
  Coventry Group:  Coventry BS, Stroud & Swindon BS
  ```

- [ ] **P2-T14** Seed Shop Direct trading names as a creditor group:
  - Shop Direct, Very, Littlewoods, Littlewoods.com → all same `parent_group = "Shop Direct Group"`

**Phase 2 verification:**
- Run seed command and confirm row count = 58 rules + 0 phantom rules
- Query `GlobalCriteria` — confirm `majority_threshold` does not exist
- Query `CreditorCriteria` — confirm WATCH/TIX/EVOLVE representatives are seeded
- Confirm TIG-01 threshold = 6000, TIG-02 threshold = 100

---

## Phase 3 — Engine: TIG rules (all cases)
**Files needed:** `criteria_engine.py`
**Goal:** Implement all 27 TIG rule methods using the JSON payload field mapping below.

### JSON payload field mapping (reference for every method in this phase)

```
total_debt          ← crm_data.total_unsecured_debt
                      fallback: sum(float(c["balance"]) for c in creditors)

disposable_income   ← financial_summary.net_balance

income_source       ← financial_summary.income_source
                      values: "payslip" | "benefits" | "self_employed" | "uc" | "cis"

has_job             ← has_job (bool)
has_uc_journal      ← has_uc_journal (bool)

client_age          ← compute from clientInfo.dateOfBirth
                      from datetime import date
                      dob = date.fromisoformat(clientInfo["dateOfBirth"])
                      age = (date.today() - dob).days // 365

payslip_docs        ← [d for d in documents if d["document_type"] == "payslip"]
bank_stmt_docs      ← [d for d in documents if d["document_type"] == "bank_statement"]

wage_slip_date      ← payslip_docs[0]["extracted_data"]["statement_date"] if exists
bank_stmt_date      ← bank_stmt_docs[0]["extracted_data"]["statement_date"] if exists
account_holder      ← bank_stmt_docs[0]["extracted_data"]["account_holder"] if exists

doc_is_fresh(doc)   ← date.fromisoformat(doc["extracted_data"]["statement_date"])
                       >= date.today() - timedelta(days=90)

gambling_monthly    ← sum amounts from gold_transactions where description matches any of:
                       ["GAMBLE","BET","CASINO","PADDY","LADBROKES","BETFAIR",
                        "WILLIAM HILL","SKYBET","CORAL","BETWAY","888","UNIBET"]

shop_direct_names   ← ["SHOP DIRECT","VERY","LITTLEWOODS"]
creation_names      ← ["CREATION","SYGMA","LASER"]

recent_shop_direct  ← gold_transactions where description contains any shop_direct_name
                       AND transaction date within 3 months

recent_creation     ← gold_transactions where description contains any creation_name
                       AND transaction date within 4 months

creditor_names      ← [c["creditor_name"].upper() for c in creditors]

is_hmrc_creditor    ← any("HMRC" in name or "HM REVENUE" in name for name in creditor_names)

hmrc_balance        ← sum balances of HMRC creditors

hmrc_is_majority    ← hmrc_balance > (total_debt * 0.5)

is_link_creditor    ← any("LINK FINANCIAL" in name for name in creditor_names)

link_balance        ← sum balances of Link Financial creditors

available_equity    ← TODO: requires property_value field not yet in payload
                       default to None; rule returns flag with TODO note when None

total_spend_2mo     ← sum abs(t["signed_amount"]) from gold_transactions
                       where transaction_type="money_out"
                       and transaction date within 60 days
                       excluding payday loan descriptions
```

### Tasks

- [ ] **P3-T1** Implement engine entry point
  ```python
  def evaluate(self, case_json: dict) -> dict:
      # 1. Parse and normalise all fields
      # 2. Run all TIG rules
      # 3. Detect WATCH/TIX/EVOLVE creditors
      # 4. Run relevant creditor-specific rules
      # 5. Return structured result
  ```

- [ ] **P3-T2** Implement `_parse_case(case_json)` helper
  - Extracts and normalises all fields listed in the mapping table above
  - Returns a clean `CaseData` dict or dataclass
  - Handles missing fields gracefully — default to None, not exception

- [ ] **P3-T3** Implement TIG-01 — minimum debt
  - `if total_debt < 6000: hard_block`

- [ ] **P3-T4** Implement TIG-02 — minimum disposable income
  - `if disposable_income <= 100: hard_block`

- [ ] **P3-T5** Implement TIG-03 — SFS guidelines
  - Flag if any expense category exceeds SFS guideline
  - SFS data not yet in payload → return flag with TODO note

- [ ] **P3-T6** Implement TIG-04 — DLA/PIP offset
  - If DLA + PIP income > 0 AND disability_expenses == 0 → hard_block
  - Fields not yet in payload → return flag with TODO note

- [ ] **P3-T7** Implement TIG-05 — wage slip required
  - If `income_source == "payslip"` or `has_job == true`:
    - Check `payslip_docs` is not empty
    - Check each slip's `statement_date` is within 90 days
    - Check one slip exists per income source (if multiple jobs)
  - Missing or outdated → hard_block

- [ ] **P3-T8** Implement TIG-06 — benefit income proof
  - If `income_source == "benefits"`:
    - Check `documents` contains benefit letter or current-year bank statement
  - Missing → hard_block

- [ ] **P3-T9** Implement TIG-07 — UC journal
  - If `income_source == "uc"` or UC income in gold_transactions:
    - Check `has_uc_journal == true`
    - Check journal date within 90 days
  - Missing/outdated → hard_block

- [ ] **P3-T10** Implement TIG-08 — self-employed income proof
  - If `income_source == "self_employed"`:
    - Check tax return document exists OR 3 months business banking
    - If newly self-employed (< 3 months in role) → hard_block
  - Missing → hard_block

- [ ] **P3-T11** Implement TIG-09 — CIS income proof
  - If `income_source == "cis"`:
    - Check CIS invoice document with 20% tax deduction flag
  - Missing → hard_block

- [ ] **P3-T12** Implement TIG-10 — proof of debt
  - For each creditor in `creditors[]`:
    - Check corresponding entry in `evidence_ledger` or `documents`
    - No proof AND balance >= 1000 → hard_block
    - No proof AND balance < 1000 → flag (if does not affect minimum debt)

- [ ] **P3-T13** Implement TIG-11 — bank statement verification
  - No bank statement → hard_block
  - Statement older than 90 days → hard_block
  - No `account_holder` in extracted_data → hard_block
  - `gambling_monthly > 1000` → hard_block
  - `gambling_monthly > 200` → flag (require GAMSTOP proof)
  - Unexplained DDs/SOs → flag

- [ ] **P3-T14** Implement TIG-12 — third-party contribution
  - If third_party_contribution exists in payload:
    - Check signed letter with required fields
  - Missing letter → hard_block
  - Field not in payload → flag with TODO note

- [ ] **P3-T15** Implement TIG-13 — previous IVA termination
  - If previous_iva == true:
    - Check termination report document exists
  - Missing → hard_block

- [ ] **P3-T16** Implement TIG-15.1 — HMRC income deductions
  - If `hmrc_is_majority` AND income/benefit deductions being taken → hard_block

- [ ] **P3-T17** Implement TIG-15.2 — HMRC previous IVA
  - If `hmrc_is_majority` AND previous IVA or bankruptcy → hard_block

- [ ] **P3-T18** Implement TIG-15.3 — HMRC late tax submissions
  - If HMRC self-assessment debt AND self-employed AND late/missing submissions → hard_block

- [ ] **P3-T19** Implement TIG-15.4 — HMRC equity
  - If `available_equity > hmrc_balance` → hard_block
  - `available_equity` is None → flag with TODO

- [ ] **P3-T20** Implement TIG-15.5 — bankruptcy return higher
  - If `bankruptcy_return > iva_return` → hard_block
  - Fields not in payload → flag with TODO

- [ ] **P3-T21** Implement TIG-15.6 — full and final from savings
  - If Full & Final funded from savings while debts unpaid → hard_block
  - Field not in payload → flag with TODO

- [ ] **P3-T22** Implement TIG-15.7 — SEISS fraud debt
  - If `seiss_debt_flag == true` → hard_block always
  - Field not in payload → flag with TODO

- [ ] **P3-T23** Implement TIG-15.8 and TIG-15.9 — HMRC info rules
  - TIG-15.8: HMRC joint debt → info, no block
  - TIG-15.9: HMRC balance < 4000 → info, no block

- [ ] **P3-T24** Implement TIG-15.10 — benefits-only income
  - If `income_source == "benefits"` AND `is_hmrc_creditor` → hard_block

- [ ] **P3-T25** Implement TIG-16 — equity exceeds liabilities
  - NON-WPM/EVERSHEDS: if `available_equity > total_debt` → flag
  - `available_equity` None → skip

- [ ] **P3-T26** Implement TIG-17 — council majority deduction
  - If council is majority creditor AND deductions being taken → flag

- [ ] **P3-T27** Implement TIG-18 — recent spending review
  - If `total_spend_2mo >= monthly_income` (excl. payday) → flag only, NOT block

- [ ] **P3-T28** Implement TIG-19 and TIG-19.1 — Shop Direct
  - TIG-19: recent_shop_direct transactions within 3 months → flag
  - TIG-19.1: Shop Direct account_age_months < 6 → hard_block

- [ ] **P3-T29** Implement TIG-20 and TIG-20.1 — Creation
  - TIG-20: recent_creation transactions within 3 months → **flag** (NOT hard_block)
  - TIG-20.1: any recent Creation/Sygma/Laser spend → **hard_block**

- [ ] **P3-T30** Implement TIG-21.1 through TIG-21.5 — Link Financial
  - TIG-21.1: Link creditor present → flag (confirm Mid SFS used)
  - TIG-21.2: `total_debt < 12000` AND Link → hard_block
  - TIG-21.3: `equity > link_balance` → hard_block
  - TIG-21.4: `benefits > 10% of household income` AND Link → hard_block
  - TIG-21.5: previous IVA failed due to arrears AND Link → hard_block

**Phase 3 verification:**
- Unit test TIG-01: debt=5999 → block, debt=6000 → pass, debt=6001 → pass
- Unit test TIG-02: di=100 → block, di=101 → pass, di=99 → block
- Unit test TIG-11: gambling=201 → flag, gambling=1001 → hard_block
- Unit test TIG-19 vs TIG-20: TIG-19 returns flag, TIG-20 returns flag, TIG-20.1 returns hard_block
- Confirm `majority_threshold` rule does not appear anywhere in engine output

---

## Phase 4 — Engine: WATCH, TIX, EVOLVE rules
**Files needed:** `criteria_engine.py` (continuation)
**Goal:** Implement all creditor-specific rules. These only run when the relevant representative is detected.

### Creditor detection logic (implement once, reuse)

```python
def _detect_representatives(self, creditors: list) -> set:
    """
    Returns set of active representatives e.g. {"WATCH", "TIX"}
    Looks up each creditor_name against CreditorCriteria.representative
    """
    names = [c["creditor_name"].upper() for c in creditors]
    reps = CreditorCriteria.objects.filter(
        creditor_name__in=names
    ).values_list("representative", flat=True)
    return set(r for r in reps if r)
```

### JSON field mapping for this phase

```
months_to_repay     ← total_debt / disposable_income (compute in engine)
vehicle_value       ← TODO: not in payload; default None
vehicle_hp_monthly  ← scan gold_transactions for HP/finance payments
                       OR explicit field if added to payload
antecedent_tx       ← TODO: not in payload; default None
car_finance_date    ← scan gold_transactions for car finance entries
children_ages       ← TODO: not in payload; default []
sustainability_para ← TODO: not in payload; default None
client_age          ← computed from clientInfo.dateOfBirth (same as Phase 3)
```

### Tasks — WATCH rules

- [ ] **P4-T1** Guard: only run WATCH rules if `"WATCH" in detected_representatives`

- [ ] **P4-T2** Implement WATCH-22.1 — vulnerability evidence
  - Vulnerability flag present but no supporting doc → flag

- [ ] **P4-T3** Implement WATCH-22.2 — debt repayable in 6 years
  - `months_to_repay = total_debt / disposable_income`
  - `if months_to_repay <= 72: hard_block`
  - Include `actual_value=months_to_repay`, `threshold=72` in result

- [ ] **P4-T4** Implement WATCH-22.3 — bankruptcy dividend higher
  - If `bankruptcy_return > iva_projected_return` → hard_block
  - Fields not in payload → flag with TODO

- [ ] **P4-T5** Implement WATCH-22.4 — equity greater than debt
  - If `available_equity > total_debt` → hard_block
  - `available_equity` None → flag with TODO

- [ ] **P4-T6** Implement WATCH-22.5 — single creditor
  - Count creditors where `float(balance) > 500`
  - If count <= 1 → **hard_block** (NOT flag)

- [ ] **P4-T7** Implement WATCH-22.6 — recent spending (3 months)
  - If ANY transaction in gold_transactions within last 90 days → hard_block
  - Use `transaction_date` field from gold_transactions

- [ ] **P4-T8** Implement WATCH-22.7 — children over 13
  - If any child age >= 13 AND no sustainability_paragraph → flag
  - `children_ages` not in payload → flag with TODO

- [ ] **P4-T9** Implement WATCH-22.8 — client age 80+
  - If `client_age >= 80` → info (WATCH abstains), no block

- [ ] **P4-T10** Implement WATCH-22.9 — vehicle value
  - If `vehicle_value > 9000` → flag
  - `vehicle_value` None → flag with TODO

- [ ] **P4-T11** Implement WATCH-22.10 — vehicle HP payment
  - If `vehicle_hp_monthly > 400` → flag
  - threshold: 400

- [ ] **P4-T12** Implement WATCH-22.11 — gambling main cause
  - If gambling identified as main cause AND no 3-month clean statements → flag

- [ ] **P4-T13** Implement WATCH-22.12 — previously proposed IVA
  - If previous IVA proposed AND I&E inconsistent AND no written explanation → flag

- [ ] **P4-T14** Implement WATCH-22.13 — antecedent transactions
  - If `antecedent_transactions == true` → hard_block, no exceptions
  - Field not in payload → flag with TODO

- [ ] **P4-T15** Implement WATCH-22.14 — car finance in last 3 months
  - Scan gold_transactions for car finance entries within 90 days
  - If found AND no valid evidence → hard_block

### Tasks — TIX rules

- [ ] **P4-T16** Guard: only run TIX rules if `"TIX" in detected_representatives`

- [ ] **P4-T17** Implement TIX-01 — Shop Direct recent spend
  - Shop Direct/Very/Littlewoods spend in last 3 months → hard_block

- [ ] **P4-T18** Implement TIX-02 — Shop Direct account age
  - Shop Direct account_age_months < 6 → hard_block

- [ ] **P4-T19** Implement TIX-03 — Creation/Sygma/Laser
  - Any spend in last 4 months → hard_block

- [ ] **P4-T20** Implement TIX-04 — vehicle HP
  - `vehicle_hp_monthly > 250` → flag
  - threshold: **250** (NOT 400 — that is WATCH's threshold)

- [ ] **P4-T21** Implement TIX-05 — deregistered creditors
  - If UKAR/Whistletree/Computershare/Landmark present → info
  - Message: "No longer represented by TIX after 30 June 2023"

- [ ] **P4-T22** Implement TIX-06 — vulnerability evidence
  - Vulnerability flag without supporting doc → flag

### Tasks — EVOLVE rules

- [ ] **P4-T23** Guard: only run EVOLVE rules if `"EVOLVE" in detected_representatives`

- [ ] **P4-T24** Implement EVOLVE-01 — equity greater than debt
  - Use 85% LTV (not 100%) to compute available equity
  - If equity > total_debt → hard_block

- [ ] **P4-T25** Implement EVOLVE-02 — single creditor
  - NatWest loan + credit card + overdraft + bounce-back = ONE lender (same parent_group)
  - If no separate lender with balance > £500 → hard_block

- [ ] **P4-T26** Implement EVOLVE-03 — vulnerability evidence
  - Vulnerability flag without supporting doc → flag

**Phase 4 verification:**
- Unit test WATCH-22.2: months=72 → block, months=71 → block, months=73 → pass
- Unit test WATCH-22.5: 1 creditor → hard_block, 2 creditors both > £500 → pass
- Unit test TIX-04 vs WATCH-22.10: same HP=300 → TIX flags, WATCH passes
- Unit test TIX-04: HP=250 → pass, HP=251 → flag
- Unit test WATCH-22.10: HP=400 → pass, HP=401 → flag
- Confirm WATCH/TIX/EVOLVE rules do NOT run when representative not in creditor list

---

## Phase 5 — Verification audit
**Files needed:** completed `criteria_engine.py` from phases 3 and 4
**Goal:** Paste the finished engine into a fresh Opus session with the verification prompt and audit every rule.

### Verification checklist

- [ ] **P5-T1** Run the full verification prompt (see `debt_checker_implementation_prompt.md`)
  against the completed engine code

- [ ] **P5-T2** Confirm these specific rules return the correct severity:
  - TIG-01 → hard_block
  - TIG-20 → flag (not hard_block)
  - TIG-20.1 → hard_block
  - WATCH-22.5 → hard_block
  - WATCH-22.8 → info
  - TIX-04 → flag with threshold=250
  - WATCH-22.10 → flag with threshold=400
  - TIG-15.8 → info
  - TIG-15.9 → info

- [ ] **P5-T3** Confirm phantom rule is gone
  - Search engine code for "majority_threshold" → must return zero results
  - Search seed file for "majority_threshold" → must return zero results

- [ ] **P5-T4** Confirm TIX and WATCH HP thresholds are different
  - TIX-04: threshold = 250
  - WATCH-22.10: threshold = 400

- [ ] **P5-T5** Run a full end-to-end test with the sample JSON payload
  - Use the JSON from `debt_checker_implementation_prompt.md`
  - Expected: TIG-01 passes (debt=6650.50), TIG-02 check (net_balance=700)
  - Expected: No WATCH/TIX/EVOLVE rules fire (no representative creditors in sample)
  - Expected: TIG-11 check on bank statement (account_holder="John Doe" → passes name check)

- [ ] **P5-T6** Confirm TODO fields are handled gracefully
  - Pass a payload with `vehicle_value` missing → engine returns flag, not exception
  - Pass a payload with `children` missing → engine returns flag, not exception
  - Pass a payload with `antecedent_transactions` missing → engine returns flag, not exception

---

## Summary: rule count targets

| Ruleset | Target count | Phase |
|---|---|---|
| TIG rules | 27 | Phase 3 |
| WATCH rules | 14 | Phase 4 |
| TIX rules | 6 | Phase 4 |
| EVOLVE rules | 3 | Phase 4 |
| **Total** | **49 implemented + 9 TODO stubs** | — |

**The 8 TODO stubs** are rules that cannot be fully implemented until these fields are added to the
JSON payload: `vehicle_value`, `children`, `antecedent_transactions`, `property_value`,
`car_finance_date`, `sustainability_paragraph_present`, `third_party_contribution`, `seiss_debt_flag`.
These should return `flag` with a clear TODO message until the upstream payload is updated.

---

## Notes for AI sessions

- Always check: does the rule exist in the source documents? If unsure, do not add it.
- Always check: is the severity correct? Flag ≠ hard_block ≠ info.
- TIG-20 is a FLAG. TIG-20.1 is the HARD BLOCK. They are different rules.
- TIX-04 threshold is 250. WATCH-22.10 threshold is 400. They are intentionally different.
- `majority_threshold` does not exist. Delete it on sight.
- Parse all `balance` fields as float — they arrive as strings in the JSON.
- When a payload field is missing, default to the least-blocking safe behaviour and note it.