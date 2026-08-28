# Case Assessment tool — payload dependencies

Fields below are read by `_parse_case()` in `debt_app/criteria_engine.py`. When the
corresponding JSON key is absent, each field falls back to **False**, **None**, or an
empty value as shown. Rules that depend on a true/non-null value therefore **do not
run their Phase 4+ logic** on production payloads until Case Assessment sends the key.

Source of truth: `criteria_engine.py` (`_parse_case` return dict and per-creditor
loop). Rule consumption verified by searching `criteria_engine.py` for reads of each
parsed key (May 2026).

---

## Client-level fields (on parsed case dict `c`)

| Field | JSON path(s) read by `_parse_case` | Default if missing | Used by (rule / phase) |
|-------|-----------------------------------|--------------------|-------------------------|
| `has_partner_on_case` | `case_json.has_partner_on_case` → else `clientInfo.has_partner_on_case` → else `client.has_partner_on_case` | `False` | Not referenced in `criteria_engine.py` rule methods yet |
| `is_currently_in_dmp` | `case_json.is_currently_in_dmp` → else `clientInfo.is_currently_in_dmp` | `False` | Not referenced in rule methods yet (`CreditorCriteria.reject_if_in_dmp` exists on ORM only) |
| `is_royal_mail_employee` | `case_json.is_royal_mail_employee` → else `clientInfo.is_royal_mail_employee` | `False` | Not referenced in rule methods yet |
| `is_police_officer` | `case_json.is_police_officer` → else `clientInfo.is_police_officer` | `False` | Not referenced in rule methods yet (`reject_if_police_employed` on ORM only) |
| `previous_iva_failed` | `case_json.previous_iva_failed` → else `clientInfo.previous_iva_failed` | `False` | Not referenced in rule methods yet (`_tig_15_8` uses `previous_iva`, not this flag) |
| `has_job` | `case_json.has_job` | `False` | `_tig_05`, `_tig_06`, `_tig_07` (income / payslip rules) |
| `has_uc_journal` | `case_json.has_uc_journal` | `False` | `_tig_08` |
| `has_property` | `case_json.has_property` | `False` | Equity helpers (`available_equity`); `_tig_16`, `_watch_22_4`, `_evolve_01` when `property_value` set |
| `has_vehicle` | `case_json.has_vehicle` | `False` | Not referenced in rule methods yet |
| `gambling_main_cause` | `crm_data.gambling_main_cause` | `False` | `_watch_22_11` (when active in engine) |
| `case_type` | `case_json.case_type` | `""` | `_tig_16` scope guard |
| `previous_iva` | `case_json.previous_iva`, else `evidence_ledger[].category == "previous_iva"` | `False` | `_tig_15_8`, `_watch_22_12` |
| `vehicle_value` | `case_json.vehicle_value` | `None` | `_watch_22_9` (`_todo_flag` when missing) |
| `children` | `case_json.children` | `[]` | `_watch_22_7` (`_todo_flag` when empty/missing) |
| `antecedent_transactions` | `case_json.antecedent_transactions` | `None` | `_watch_22_13` (`_todo_flag` when missing) |
| `seiss_debt_flag` | `case_json.seiss_debt_flag` | `None` | `_tig_15_7` (`_todo_flag` when missing) |
| `third_party_contribution` | `case_json.third_party_contribution` | `None` | `_tig_12` (`_todo_flag` when missing) |
| `sustainability_paragraph_present` | `case_json.sustainability_paragraph_present` | `None` | `_watch_22_7` path (`_todo_flag` when missing) |
| `bankruptcy_return` | `case_json.bankruptcy_return` | `None` | `_tig_15_5`, `_watch_22_3` (`_todo_flag` when missing) |
| `sfs_expenditure_breakdown` | `case_json.sfs_expenditure_breakdown` | `None` | `_tig_03` (`_todo_flag` when missing) |
| `disability_income` | `case_json.disability_income` | `None` | `_tig_04` (`_todo_flag` when missing) |
| `disability_expenses` | `case_json.disability_expenses` | `None` | `_tig_04` (`_todo_flag` when missing) |
| `income_deductions_active` | `case_json.income_deductions_active` | `None` | `_tig_15_1` (`_todo_flag` when missing) |
| `benefit_income_breakdown` | `case_json.benefit_income_breakdown` | `None` | `_tig_21_4` (`_todo_flag` when missing) |
| `vulnerability_claimed` | `case_json.vulnerability_claimed` | `None` | `_watch_22_1`, `_tix_06`, `_evolve_03` (`_todo_flag` when missing) |
| `property_value` | `case_json.property_value` | `None` | `_tig_15_4`, `_tig_16`, `_tig_21_3`, `_watch_22_4`, `_evolve_01` |
| `proposed_dividend_pence` | `case_json.proposed_dividend_pence` | `None` | Dividend advisory in `assess_case` (not a TIG rule id) |
| `override_code` | `case_json.override_code` | `None` | Override demotion in `assess_case` |
| `override_reason` | `case_json.override_reason` | `None` | Override demotion in `assess_case` |
| `override_by` | `case_json.override_by` | `None` | Override demotion in `assess_case` |

---

## Per-creditor fields (on each `c["creditors"][i]`)

Parsed from each element of `case_json.creditors[]`.

| Field | JSON path | Default if missing | Used by (rule / phase) |
|-------|-----------|-------------------|-------------------------|
| `is_joint` | `creditors[i].is_joint` | `False` | Not referenced in rule methods yet |
| `last_payment_date` | `creditors[i].last_payment_date` (ISO date string stored on `c`) | `None` | Not referenced in rule methods yet |
| `months_since_last_payment` | Derived from `creditors[i].last_payment_date` via `months_since_last_payment_from_date()` | `None` | Not referenced in rule methods yet |
| `first_payment_made` | `creditors[i].first_payment_made` | `False` | Not referenced in rule methods yet (`reject_if_never_made_payment` on ORM only) |
| `vehicle_arrears_months` | `creditors[i].vehicle_arrears_months` | `None` | Not referenced in rule methods yet (`vehicle_arrears_repossession_months` on ORM only) |
| `ie_matches_loan_application` | `creditors[i].ie_matches_loan_application` | `None` | Not referenced in rule methods yet |
| `arrangement_confirmed_before_proposing` | `creditors[i].arrangement_confirmed_before_proposing` | `False` | Not referenced in rule methods yet |
| `client_still_has_asset_in_possession` | `creditors[i].client_still_has_asset_in_possession` | `False` | Not referenced in rule methods yet |
| `is_grant_overpayment` | `creditors[i].is_grant_overpayment` | `False` | Not referenced in rule methods yet |
| `guarantee_called_up` | `creditors[i].guarantee_called_up` | `None` | Not referenced in rule methods yet |
| `has_ccj` | `creditors[i].has_ccj` | `False` | `_tig_10`; also `has_ccj_any` on `c` |
| `account_age_months` | `creditors[i].account_age_months` | `None` | `_tig_19_1`, `_tix_02` (Shop Direct age) |
| `last_transaction_date` | `creditors[i].last_transaction_date` | `None` | Not used directly in current rules |
| `linked_creditor` | `creditors[i].linked_creditor` | `None` | `_tig_10` |
| `covers_months` | `creditors[i].covers_months` | `None` | `_tig_10` |
| `parent_group` | `creditors[i].parent_group` (payload or DB enrich) | `None` | `_watch_22_5`, `_evolve_02` |
| `representative` | `creditors[i].representative` (payload or DB enrich) | `None` | Representative gating in `assess_case` |
| `min_dividend_pence` | `creditors[i].min_dividend_pence` (payload or DB enrich) | `None` | Dividend advisory in `assess_case` |
| `debt_type_normalised` | Derived from `creditors[i].creditor_type` via `normalise_debt_type()` | `UNKNOWN` if type missing/unknown | Not referenced in rule methods yet |

---

## Notes for CA tool owners

1. **Precedence:** Top-level `case_json` keys win over `clientInfo` / `client` for client flags where `_parse_case` nests `.get()` calls that way (see `has_partner_on_case`, `is_currently_in_dmp`, etc.).
2. **Assess endpoint shape:** Live assess payloads use `clientInfo` (camelCase) and `creditors[]` per `debt_app/views/assess_view.py` validation — not the `client` / `debts` keys used in some internal sketches.
3. **ORM vs parser:** `ClientFlags` and extended `Voter` columns exist in `debt_app/models.py` for persistence; the running engine only sees the parsed dict from JSON today.
