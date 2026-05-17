# Debt Criteria Service — Implementation Plan (current)

This plan matches the **repository as implemented today** (`debt_app/criteria_engine.py`, `_parse_case`, `assess_case`, JWT + direct assess APIs). It supersedes informal or historical phase docs that assumed rules were not yet built.

**Companion docs:** [ARCHITECTURE.md](ARCHITECTURE.md) (system design, **§11 spec vs code audit**), [CASE_ASSESSMENT_PAYLOAD.md](../CASE_ASSESSMENT_PAYLOAD.md) (HTTP JSON contract).

---

## Current baseline (facts)

- **58 rules** are implemented as Python functions; **TIG** always runs; **WATCH / TIX / EVOLVE** run when representatives are detected via `CreditorCriteria` (exact creditor / trading name match).
- **`POST /api/v1/assess/`** validates a **minimal** payload (`application_id`, `financial_summary`, non-empty `creditors`) then runs the engine.
- **`GlobalCriteria`** supplies some thresholds (e.g. equity rules); others are hard-coded defaults.
- **Resolved in Phase A:** JSON fields listed in Phase A / **§11.1** are copied onto the rule dict **`c`** by `_parse_case` (mortgage row normalisation, DOB aliases). Remaining stubs depend on **Group A/B** and other top-level fields being **present on each assess request** when those rules apply.

---

## Phase A — Parser: wire `case_json` → `c` (backend; blocks correct evaluation)

**Status:** Implemented in `_parse_case` (see `debt_app/criteria_engine.py` and `tests/test_criteria_engine.py::TestParseCasePhaseAFields`).

**Goal:** Anything Case Assessment sends must be visible to rule functions on **`c`** (`_parse_case` return value).

| Task | Detail | Verification |
|------|--------|----------------|
| **A1** | Add `sfs_expenditure_breakdown` from `case_json` onto `c` | TIG-03 evaluates real rows instead of perpetual `_todo_flag` |
| **A2** | Add `disability_income`, `disability_expenses` | TIG-04 same |
| **A3** | Add `income_deductions_active` | TIG-15.1 same |
| **A4** | Add `benefit_income_breakdown` | TIG-21.4 breakdown path same |
| **A5** | Add `vulnerability_claimed` | WATCH-22.1, TIX-06, EVOLVE-03 same |
| **A6** | Add top-level `mortgage_outstanding` (or derive) so `c.get("mortgage_outstanding")` works | Equity rules use CAT top-level field when present |
| **A7** | Normalize **`mortgage_details`**: sum `balance` **or** `outstanding_balance` per row | Equity matches Aryza/CAT shape; update `CASE_ASSESSMENT_PAYLOAD.md` |
| **A8** | Accept **`clientInfo.date_of_birth`** as alias for **`dateOfBirth`** | Age-based rules (e.g. WATCH-22.8) work with documented payload |

**Exit criteria:** Unit tests where each field is present in JSON and the corresponding rule returns **pass** or a **non-TODO** triggered result (not the literal `_todo_flag` message for that field).

---

## Phase B — Case Assessment Tool & contract (integration)

The **Case Assessment tool can send** the fields below; Phase B is about **always emitting** them when the case requires those rules, **shape and naming** matching this service’s `_parse_case`, and proving that in staging.

**Goal:** Each production-style assessment sends complete, correctly shaped JSON per [CASE_ASSESSMENT_PAYLOAD.md](../CASE_ASSESSMENT_PAYLOAD.md).

| Task | Detail |
|------|--------|
| **B1** | Emit **Group A–D** fields (property, conduct, vulnerability/household, income) per payload doc |
| **B2** | Align **DOB** and **`previous_iva`** with what `_parse_case` reads (after A8 / doc update) |
| **B3** | Ensure **`gold_transactions`** include `transaction_date` or `date` for time-window rules |
| **B4** | Set **`has_property`** when property/equity logic should apply |

**Exit criteria:** Staging runs with real-style payloads (with Case Assessment supplying Groups A–D where applicable); count of `_todo_flag` results trends to **zero** for production-like cases; stub table in `CASE_ASSESSMENT_PAYLOAD.md` matches observed behaviour.

---

## Phase C — Verification & regression

| Task | Detail |
|------|--------|
| **C1** | Expand **`tests/`** with golden JSON fixtures (anonymised) for critical paths: equity, antecedents, HMRC majority, Link, Shop Direct, WATCH-only |
| **C2** | Add optional metric/log: **`_todo_flag` rate** per `application_id` in staging |
| **C3** | Run **`pytest`** in CI on every change touching `criteria_engine.py` or `_parse_case` |

**Exit criteria:** CI green; stakeholders sign off sample pack of cases (expected blocked / flagged / pass).

---

## Phase D — Security & operations (microservice hardening)

| Task | Detail |
|------|--------|
| **D1** | Protect **`POST /api/v1/assess/`** (API key, mTLS, or private network + gateway only) |
| **D2** | TLS termination, rate limits, structured logs (`application_id`, `overall`, block/flag counts) |
| **D3** | Readiness checks beyond **`/api/ping/`** if MySQL `aryza` is required in an environment |
| **D4** | Remove or gate **`print`** in `debt_project/urls.py` for production |
| **D5** | Optional: mount **Django admin** or internal CRUD for `CreditorCriteria` / `GlobalCriteria` |

---

## Phase E — Spec parity (manager docs vs code)

**Goal:** Align behaviour with **WATCH CRITERIA.docx**, **TIG CRITERIA.docx**, and **TIP** checklist where compliance agrees the **spec** is authoritative.

Use the matrix in [ARCHITECTURE.md §11.2](ARCHITECTURE.md) as the backlog. High-impact examples:

| Item | Typical action |
|------|----------------|
| TIG-04 severity | Doc: hard block; code: flag — decide and change one side |
| WATCH-22.3 severity | Doc: hard block; code: flag |
| WATCH-22.4 test | Doc: equity vs **total debt**; code: equity vs **threshold** — implement doc test or re-label rule |
| WATCH-22.9 amount | Doc £9,000 vs code default £5,000 — seed `GlobalCriteria` or change default |
| WATCH-22.11 | Use **`gambling_main_cause`** from CRM when implementing doc condition |
| TIG-06 | Financial year vs calendar year for bank-statement fallback |

**Exit criteria:** Signed rule-by-rule matrix (Rule ID | Spec | Code | Decision | Owner).

---

## Phase F — Audit & product depth

| Task | Detail |
|------|--------|
| **F1** | Persist **`CriteriaDecision`** for direct assess if full audit is required |
| **F2** | Stamp **engine / ruleset version** on stored decisions and optionally API response |
| **F3** | Written **override** policy (who may set `MANAGER_REVIEW` / `COMPLIANCE_SIGN_OFF` / `SENIOR_CASEWORKER`) |
| **F4** | UX copy for **`indeterminate`** (`TIG-10`, `TIG-07`, `WATCH-22.1`) |
| **F5** | **`frontend/`** workflows against JWT APIs if in scope |

---

## Dependency order

```text
Phase A (parser)  →  Phase B (CAT payload)  →  Phase C (verification)
        ↘                                    ↗
         Phase D (security) can start in parallel after A for internal deploys
Phase E (spec parity) after C when real payloads exercise rules
Phase F after production audit requirements are known
```

---

## Quick checklist (copy for tickets)

- [x] **A** `_parse_case` passes Phase A / §11.1 fields (see `ARCHITECTURE.md`)  
- [ ] **B** Production payloads include Groups A–D + transaction dates + `has_property` where rules apply (Case Assessment can supply; integration must send)  
- [ ] **C** Golden tests + CI + sample pack sign-off  
- [ ] **D** Auth + logging + no debug print in URLs  
- [ ] **E** Spec/code matrix closed for must-fix rows  
- [ ] **F** Versioning + override policy + optional persistence  

---

*This plan is maintained to reflect the codebase. When `_parse_case`, rules, or manager docs change, update Phase A/E and [ARCHITECTURE.md](ARCHITECTURE.md) §11 together.*
