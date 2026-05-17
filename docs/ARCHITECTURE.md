# Debt Criteria Engine — Architecture, Rules, Gaps & Implementation Plan

This document describes how the **Debt Criteria Assessment** backend is structured, how rules are implemented, how it relates to manager reference materials (WATCH / TIG / TIP), what is **missing** for a complete case pipeline, and a **next implementation plan**.

**Related files:** `README.md`, `CASE_ASSESSMENT_PAYLOAD.md`, `debt_app/criteria_engine.py`, `debt_app/views/assess_view.py`, `debt_app/models.py`, [CRITERIA_IMPLEMENTATION_PLAN.md](CRITERIA_IMPLEMENTATION_PLAN.md).

---

## 1. Purpose

The system evaluates **IVA-style case JSON** against **58 business rules** (TIG always; WATCH / TIX / EVOLVE when those representatives appear on creditors). Output is grouped into **hard_blocks**, **flags**, **info**, and **passed**, plus **overall** (`pass` | `flagged` | `indeterminate` | `blocked`), optional **override** metadata, and **advisory_notes** (e.g. dividend minimums).

---

## 2. High-level architecture

| Layer | Responsibility |
|--------|----------------|
| **HTTP — direct assess** | `POST /api/v1/assess/` (`debt_app/views/assess_view.py`): JSON parse, **minimal** payload validation, `detect_representatives` + `assess_case`, JSON response. CSRF-exempt plain Django view. **No authentication** (must be restricted by network/API gateway in production). |
| **HTTP — criteria API** | DRF + JWT: Aryza-backed assess, creditors, rules, assessment history (`debt_app/views/criteria_views.py`, URLs in `debt_project/urls.py`). |
| **Orchestration** | `assess_case()` in `criteria_engine.py`: optional DB enrichment of creditors → `_parse_case()` → run rule functions → **override** demotion of hard blocks → **indeterminate** detection → assemble result. |
| **Rules** | One function per rule (`_tig_01`, `_watch_22_2`, …); each returns `RuleResult`. Rule IDs align with `GlobalCriteria.rule_key` (e.g. `TIG-15.10`). |
| **Data** | SQLite default; `CreditorCriteria` / `GlobalCriteria` for configuration; optional MySQL `aryza` for case fetch; `CriteriaDecision` for persisted audits. |

### Engine pipeline (from code)

1. **`_enrich_creditors_from_db`** — For each `creditors[].creditor_name`, exact match to `CreditorCriteria` fills `parent_group`, `representative`, `min_dividend_pence` when not already supplied in JSON.
2. **`detect_representatives`** — Union of representatives for all matched active creditors (exact name / trading name only).
3. **`_parse_case`** — Single normalized dict: totals, disposable income, document subsets, HMRC/council/Link subsets, gambling totals, equity inputs, TODO fields, overrides, evidence ledger, etc.
4. **Rule execution** — TIG list always; WATCH / TIX / EVOLVE lists gated by detected set.
5. **Overrides** — Valid `override_code` + non-empty `override_reason` + `override_by` demotes **all** current hard blocks to flags.
6. **Indeterminate** — No hard blocks, but flags include any of `TIG-10`, `TIG-07`, `WATCH-22.1` → `overall = indeterminate`.

---

## 3. How each rule is implemented

| Mechanism | Description |
|-----------|-------------|
| **Parsing** | `_parse_case(case_json)` never raises; missing optional fields become `None` or empty collections. |
| **Rule body** | Reads only the parsed dict `c`. No ORM inside rule functions. |
| **Severities** | `hard_block`, `flag`, `info`, `pass`. Bucketing in `assess_case._run()`. |
| **Stubs** | `_todo_flag(rule_id, field_name)` — **flag** with a TODO message when a required payload field is absent so the engine does not silently pass a strict check. |
| **Constants** | Named creditor sets and keywords (e.g. Shop Direct, HMRC, gambling) live in `criteria_engine.py` as frozensets/lists. |
| **Thresholds** | Some rules read `GlobalCriteria` for active/threshold (see seed commands and models); others embed numbers in code — check each rule. |

### Direct assess validation (narrower than full payload)

Required by `assess_view._validate_direct_assess_payload`:

- `application_id` — non-empty string  
- `financial_summary` — dict with numeric `net_balance`, `total_income`  
- `creditors` — non-empty list; each item dict with non-empty `creditor_name` string and numeric `balance` ≥ 0  

All other fields are optional at HTTP layer but may be required for specific rules to evaluate.

---

## 4. Rule families (inventory)

| Family | When it runs | Rule IDs (orchestrated in `assess_case`) |
|--------|----------------|---------------------------------------------|
| **TIG** | Every case | `TIG-01` through `TIG-21-5` (inclusive lists in `criteria_engine.py`) |
| **WATCH** | `"WATCH"` in detected representatives | `WATCH-22.1` … `WATCH-22.14` |
| **TIX** | `"TIX"` in detected representatives | `TIX-01` … `TIX-06` |
| **EVOLVE** | `"EVOLVE"` in detected representatives | `EVOLVE-01` … `EVOLVE-03` |

Authoritative behaviour (messages, thresholds, severities) is **each function** in `debt_app/criteria_engine.py`.

---

## 5. Reference documents (manager materials)

These are **business specifications** used to build and validate the engine; they are not loaded at runtime.

| Document | Role |
|----------|------|
| **WATCH CRITERIA.docx** | Section 22 rules: vulnerability evidence, repay within 6 years, bankruptcy vs IVA return, equity vs debt, single creditor, recent spending, children/sustainability, age 80+, vehicle value/HP, gambling clean statements, previous proposal, antecedent transactions, recent car finance, etc. Stresses documents vs CRM vs notes; mentions manager overrides. |
| **TIG CRITERIA.docx** | Broad TIG playbook: £6k debt, £100 DI, SFS, DLA/PIP, income proofs (wage slip, benefits, UC journal, self-employed, CIS), bank statements, gambling/GAMSTOP narrative, proof of debts, HMRC/council/Link/Shop Direct/Creation, equity/bankruptcy, SEISS, third-party letters, previous IVA, etc. Includes editorial “Phase 2” ideas (e.g. SFS in-tool). |
| **TIP CRITERIA & VOTING HISTORY.xlsx** | Condensed checklist (income, bank statements, gambling, POD, HMRC, councils, WATCH recent spend, Shop Direct/Creation/Link, equity, SEISS, etc.). Maps conceptually to TIG/WATCH-style rules already encoded; **TIP** is not a separate engine family — the code uses **TIG / WATCH / TIX / EVOLVE**. |

**Note:** Word specs may describe a rule as **hard block** while the current code uses **flag** or **TODO** until data exists. The **code** is the runtime source of truth; differences should be tracked and reconciled deliberately.

---

## 6. Payload contract & Case Assessment integration

Full field reference: **`CASE_ASSESSMENT_PAYLOAD.md`**.  
The **Case Assessment tool can send** all documented fields; the engine only sees what arrives on each **`POST` body**. **`_parse_case`** copies Group D / vulnerability / mortgage fields listed in **§11.1** onto **`c`**. Other documented fields (e.g. `property_value`, `antecedent_transactions`) must appear in JSON when those rules should run — see **§11.1** and the stub table in `CASE_ASSESSMENT_PAYLOAD.md`.

### 6.1 Stub rules (fields missing → `_todo_flag`)

When the **submitted payload** omits a field a rule needs, that rule returns TODO flags instead of real evaluation (even though Case Assessment *can* supply the field). See stub table in `CASE_ASSESSMENT_PAYLOAD.md` (§ Stub Rules Reference). In particular:

- **Six rules** are **hard_block** in spec when data exists, but **do not enforce** as hard blocks until payload is complete — they appear as TODO **flags** when fields are missing (equity, antecedent transactions, etc.).
- Groups **A–D** in `CASE_ASSESSMENT_PAYLOAD.md` list fields required to unblock those stubs (`property_value`, `antecedent_transactions`, `vulnerability_claimed`, `sfs_expenditure_breakdown`, …).

### 6.2 Payload vs parser alignment (documentation / tool fixes)

| Issue | Detail |
|-------|--------|
| **Date of birth** | `_parse_case` accepts **`clientInfo.dateOfBirth`** or **`clientInfo.date_of_birth`** for age (same precedence as documented aliases). |
| **Previous IVA** | Engine reads **top-level** `previous_iva` (and `evidence_ledger` category). Payload doc emphasises `clientInfo.previous_iva`. Ensure the producer sends what the parser reads. |
| **Mortgage balance** | Parser sums each row using **`balance` if present, else `outstanding_balance`**, and sets **`mortgage_outstanding`** on `c` from top-level or that sum. |

---

## 7. Production readiness (honest assessment)

**Strong:** Clear separation parse → rules → aggregate; tests; Docker; JWT for protected APIs; seedable criteria; audit model for Aryza path.

**Gaps before treating as production for automated creditor decisions:**

1. **Incomplete payloads** — Critical hard blocks may not run; TODO flags dominate when Group A–D fields are **omitted** on a request. Case Assessment can send them; **integration and workflow** must ensure they are included whenever those rules should apply.  
2. **Unauthenticated direct assess** — Needs API gateway auth, TLS, rate limits, monitoring.  
3. **Spec vs implementation** — Reconcile Word/excel narratives with code severities (example: DLA/PIP rule may differ between spec and `TIG-04`).  
4. **Operations** — Admin UI optional; rule versioning; override governance and full audit trail policies.  
5. **Single source for thresholds** — Mix of DB thresholds and hard-coded values — document and optionally centralise.

---

## 8. What is missing (checklist)

### 8.1 Case Assessment Tool / integration

Case Assessment **supports** sending the fields below; close the gap by **always including** them on the assess payload when the case needs the related rules (and by mapping CRM → JSON consistently).

- [ ] **Group A** — `property_value`, mortgage data (`mortgage_details` with `balance` and/or `outstanding_balance` per `CASE_ASSESSMENT_PAYLOAD.md`; optional top-level `mortgage_outstanding`).  
- [ ] **Group B** — `antecedent_transactions`, `bankruptcy_return`, `seiss_debt_flag`, `full_and_final_from_savings`.  
- [ ] **Group C** — `vulnerability_claimed`, `children`, `third_party_contribution`, `sustainability_paragraph_present`.  
- [ ] **Group D** — `sfs_expenditure_breakdown`, `disability_income`, `disability_expenses`, `income_deductions_active`, `benefit_income_breakdown`, `vehicle_value`.  
- [ ] **DOB** — `clientInfo.dateOfBirth` and/or `clientInfo.date_of_birth` (engine accepts both).  
- [ ] **`previous_iva`** — align producer with engine: top-level and/or `evidence_ledger`; note `clientInfo.previous_iva` in payload doc if the tool maps it to top-level before assess.  
- [ ] **`has_property`** when property/equity rules should apply.  
- [ ] **`gold_transactions`** — `transaction_date` or `date` where time-window rules apply.

### 8.2 Engine / backend (optional follow-ups)

- [x] **`_parse_case`** — §11.1 fields and mortgage row normalisation (`balance` / `outstanding_balance`), top-level `mortgage_outstanding` or derived; **`clientInfo.date_of_birth`** alias (see **§11.1** / Phase A in `CRITERIA_IMPLEMENTATION_PLAN.md`).  
- [ ] Reconcile **TIG-04** (and similar) **severity** with written TIG criteria if compliance requires hard block.  
- [ ] Optional: secure `POST /api/v1/assess/` with service token or mutual TLS.  
- [ ] Mount Django admin or internal tooling for `GlobalCriteria` / `CreditorCriteria` if not using API-only admin flows.  
- [ ] Rule/engine **version** stamped on `CriteriaDecision.decision_output` for audit.

### 8.3 Product / compliance

- [ ] Written policy for **override** use (who may use `MANAGER_REVIEW` / `COMPLIANCE_SIGN_OFF` / `SENIOR_CASEWORKER`).  
- [ ] User-facing copy for **indeterminate** outcomes (TIG-10 / TIG-07 / WATCH-22.1).  
- [ ] Sign-off that **58 rules** cover all items in WATCH/TIG/TIP references (gap analysis workshop).

---

## 9. Next implementation plan (recommended order)

### Phase 1 — Unblock real rule evaluation (highest impact)

0. **`_parse_case` completeness** — Done for §11.1 / mortgage / DOB aliases (see `CRITERIA_IMPLEMENTATION_PLAN.md` Phase A).  
1. **Payload on the wire** — Ensure Case Assessment (or the service calling assess) **includes** Groups A–D on each request that needs them; keep `CASE_ASSESSMENT_PAYLOAD.md` aligned with observed JSON and **`previous_iva`** mapping.  
2. **Staging verification** — Run regression `pytest` plus a suite of real anonymised payloads; confirm hard blocks fire for equity, antecedents, etc.  
3. **Monitor TODO rate** — Log or metric: count of `_todo_flag` messages per assessment; drive to zero for production creditors.

### Phase 2 — Security & operations

1. Protect **`/api/v1/assess/`** (API key, OAuth2 client credentials, or private network only).  
2. **Rate limiting** at gateway; structured logging (application_id, overall, counts).  
3. **Health + readiness** (DB, `aryza` pool if used).  
4. Enable **Django admin** or internal CRUD for criteria maintenance if operators need it.

### Phase 3 — Spec parity & maintainability

1. **Rule-by-rule matrix** — Spreadsheet: Rule ID | Spec severity | Code severity | Payload fields | Owner.  
2. Adjust code or spec where mismatches are bugs (e.g. DLA/PIP hard block vs flag).  
3. Move volatile thresholds toward **DB** where business wants runtime tuning without deploy.

### Phase 4 — Product depth

1. **CriteriaDecision** adoption for all paths that need audit (including direct assess if required).  
2. **Versioning** — Engine version + ruleset hash on each stored decision.  
3. Frontend (Vite app) workflows wired to authenticated APIs where appropriate.

---

## 10. Quick reference — key files

| File | Purpose |
|------|---------|
| `debt_app/criteria_engine.py` | `assess_case`, `_parse_case`, all rule functions, `detect_representatives` |
| `debt_app/views/assess_view.py` | `POST /api/v1/assess/` validation and response shape |
| `debt_app/models.py` | `CreditorCriteria`, `GlobalCriteria`, `CriteriaDecision`, … |
| `CASE_ASSESSMENT_PAYLOAD.md` | Request/response contract, stub table |
| `README.md` | Setup, API summary, tests |

---

## 11. Spec vs code audit (WATCH / TIG / TIP vs `criteria_engine.py`)

Cross-check against manager materials (**WATCH CRITERIA.docx**, **TIG CRITERIA.docx**, **TIP CRITERIA & VOTING HISTORY.xlsx**) and `CASE_ASSESSMENT_PAYLOAD.md`. **Runtime behaviour is defined by code**, not the Word files; this table tracks deliberate or accidental gaps.

### 11.1 Parser → rule dict `c` (Phase A wired)

Rule functions read **`c`** — the object returned by **`_parse_case` only**. The following are **copied from `case_json`** (with mortgage normalisation per §6.2). Omitting a key leaves `None` where rules still use `_todo_flag` until the producer sends the field.

| Field (on `c`) | Consumed by | Notes |
|----------------|-------------|--------|
| `sfs_expenditure_breakdown` | TIG-03 | From top-level `case_json` |
| `disability_income`, `disability_expenses` | TIG-04 | From top-level |
| `income_deductions_active` | TIG-15.1 | From top-level |
| `benefit_income_breakdown` | TIG-21.4 | From top-level |
| `vulnerability_claimed` | WATCH-22.1, TIX-06, EVOLVE-03 | From top-level |
| `mortgage_outstanding` | TIG-15.4, TIG-16, TIG-21.3, WATCH-22.4, EVOLVE-01 | Top-level if set, else **derived** as sum of per-row mortgage amounts (see §6.2) |
| `mortgage_balance` | `available_equity`, shared with equity rules | Sum per row: `balance` if present, else `outstanding_balance` |

### 11.2 Document vs implementation — mismatches or simplifications

| Topic | Manager / TIP intent | Current code | Notes |
|-------|----------------------|--------------|--------|
| **TIG-04** | Hard block if DLA/PIP income and no disability expenses | **`flag`** when triggered | Stricter in written TIG doc |
| **WATCH-22.3** | Hard block if bankruptcy return higher than IVA | Same numeric comparison as TIG-15.5 but **`flag`** | Stricter in WATCH doc |
| **WATCH-22.4** | Hard block if **equity > total unsecured debt** | Hard block if **equity > threshold** (from `GlobalCriteria` / default £), not vs `total_debt` | **Different test** than doc |
| **WATCH-22.9** | Vehicle over **£9,000** | Default **£5,000** unless `GlobalCriteria.WATCH-22.9` = 9000 | Align DB seed or code default |
| **WATCH-22.11** | Gambling as **main cause** + clean statements | Any **`gambling_monthly > 0`**; `gambling_main_cause` on `c` unused in rule | Narrower condition in doc |
| **TIG-06** | Benefit proof in **current financial year** | Bank statement “current year” uses **calendar year** substring on statement date | Can diverge from UK tax year |
| **TIG-05** | One wage slip **per** employment income | Single payslip list / date check | Simplified vs multi-job doc |
| **TIG-08** | Newly self-employed ≥ 3 months in job, etc. | Tax return **or** ≥3 `bank_stmt_docs` | No job-tenure check |
| **TIG-15.3** | HMRC SA + late submissions / HMRC confirmation | **Tax return document present** as proxy | Weaker than operational doc |
| **TIG-21.5** | Link + previous IVA **failed due to arrears** | **`previous_iva` only** (failure reason TODO in code) | Can over-flag vs doc |
| **WATCH-22.6** | Recent spend from **credit reports / statements** | **`gold_transactions`** only, `transaction_type == "money_out"` | Different data source |

### 11.3 Broadly aligned (subject to payload + parser fixes)

Examples where code matches the spirit of docs/TIP if inputs are present and parsed: **TIG-01** (£6k), **TIG-02** (£100 DI), **TIG-10** proof bands / CCJ flag, **TIG-11** gambling £200 flag / £1000 block, **WATCH-22.2** (`total_debt / disposable_income` vs 72 months), **WATCH-22.5** / **EVOLVE-02** single-lender logic, **WATCH-22.13** antecedents (when field wired), **TIG-21.2** Link £12k debt floor, Shop Direct / Creation / TIX thresholds as coded.

### 11.4 TIP spreadsheet

The xlsx is a **checklist** (tax code, GAMSTOP, POD granularity, CRM vs documents, etc.). The engine covers **themes** (income proof, bank statements, gambling, HMRC, Link, recent spend) but **not every bullet** line-for-line; treat TIP as input to a future gap workshop (see §8.3).

---

*Last updated: includes §11 spec vs code audit. Update when `_parse_case`, rule severities, or manager docs change.*
