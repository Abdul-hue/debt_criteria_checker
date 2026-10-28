# Case Assessment tool — payload dependencies

Fields below are read by `_parse_case()` in `debt_app/criteria_engine.py`. When the
corresponding JSON key is absent, each field falls back to **False**, **None**, or an
empty value as shown. Rules that depend on a true/non-null value therefore **do not
run their Phase 4+ logic** on production payloads until Case Assessment sends the key.

Source of truth: `criteria_engine.py` (`_parse_case` return dict and per-creditor
loop). Rule consumption verified by searching `criteria_engine.py` for reads of each
parsed key (May 2026).

**Contract notes from the September 2026 integration audit** (the Case Assessment
tool now sends exactly this):

* Dates are ISO `YYYY-MM-DD`. `_days_since` parses nothing else.
* `gold_transactions: null` means "no bank data" (`has_open_banking` False, every
  transaction rule flags for a manual check); `[]` means "scanned, nothing found".
* `creditors[].first_payment_made` and `creditors[].client_still_has_asset_in_possession`
  are tri-state: `true` / `false` / absent-or-`null` = not known. `_parse_case` keeps
  `null` (it used to coerce it to `false`, which is the REJECT value).
* Secured creditors are sent WITH `is_secured: true`. `total_debt`, the 75% majority,
  `_count_qualifying_lenders`, `_representative_balance_majority`, dividend minimums
  and `detect_representatives` all exclude them; every returned position carries
  `is_secured` so the caller can keep them out of its vote table.
* `uc_journal_date` is sent (ISO) so TIG-07 can apply its 90-day test.
* TIG-10 treats `"<placeholder> (creditor not yet identified)"`, `"OTHER"`, `"CCJ"` and
  `"Unknown Creditor"` as unidentified debts. WATCH-22.5 / EVOLVE-02 leave such rows out of
  the lender count and FLAG (not block) when an unidentified creditor over £500 could be the
  missing second lender.
* `children[]` is `[{"age": years | null, "dob": ISO | null}]`; `age: null` is a child the
  household counts know about but whose date of birth is not on record, and WATCH-22.7 FLAGS
  it rather than treating it as under 13. Threshold stays "over 13" (see the rule's docstring
  for the wording conflict in this repo's own docs).
* `GlobalCriteria.is_active=False` now disables a rule by the id it EMITS as well as the
  function-derived id (TIG-11-GAMBLING, the TIG-HMRC-* rules and TIG-SHOP-DIRECT-4MO-REVIEW
  could not be disabled before).
* `get_creditor_by_trading_name` is memoised per request (`helpers.creditor_lookup_cache`):
  a 26-creditor case went from 28 s to 2 s on `/api/v1/assess/`.
* `creditors[].monthly_repayment` (the declared instalment) is read for vehicle-HP creditors:
  `vehicle_hp_monthly` is the larger of the bank scan and the declared figure, and
  WATCH-22.10 / TIX-04 evaluate the declared figure when there is no bank data. The bank scan
  also matches the case's own vehicle-HP lender names, not only the generic keyword list.

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

---

## Proposed: Case Rejection Criteria (Missing Evidence) — October 2026

**Status: PROPOSED — awaiting CAT team sign-off.** Phase 1 is in: `_parse_case` reads every field
below (tests: `debt_app/tests/test_missing_evidence_parsing.py`), but **no rule uses them yet**, so
sending them changes no assessment result. The parser also derives `self_employed_months`
(completed calendar months to `assessment_date`) and `ccj_creditors` / `ccj_balance` /
`ccj_is_majority` (CCJ debt > 50% of unsecured debt; a CCJ is a creditor with `has_ccj: true`, a
`creditor_type` of "CCJ", or Aryza's "CCJ" placeholder name). An out-of-range `div_returned`
(e.g. `25` for 25%) is ignored and logged, not converted.

The new "Case Rejection Criteria (Missing Evidence)" requirement splits between the two systems:

* **Criteria engine:** decides whether each check applies to the case (HMRC, self-employed, council
  status, arrears type, CCJ majority), whether the evidence is in place, and calculates the council
  DIV requirement. Results come back as `hard_block` / `flag` as today.
* **CAT:** collects the evidence (POD uploads, call sheets, creditor-call outcomes, the DIV a
  council returned), sends the fields below, blocks the case at drafting / SIP, and shows
  Required DI / Actual DI / Shortfall.

A check only runs when its trigger applies. A case with no HMRC debt is never asked for an HMRC
call sheet.

### Tri-state convention

Every new evidence flag is tri-state, matching `first_payment_made` above:

| Value sent | Meaning | Engine behaviour when the check applies |
|------------|---------|------------------------------------------|
| `true` | Evidence is in place | Pass |
| `false` | Evidence has been confirmed missing | Return the case (or flag, where the table says so) |
| absent / `null` | CAT does not know | Flag for the caseworker to confirm. Never returns the case. |

CAT must send `false` only when it has positively established that the evidence is missing. If it
sends `false` because the field is not wired up yet, cases will be returned wrongly.

### Client-level fields

| Field | Type | Meaning | Default if missing | Will be used by |
|-------|------|---------|--------------------|-----------------|
| `has_call_sheet` | bool / null | A client call sheet has been completed and uploaded | `null` | Self-employed (12+ months) call-sheet rule only. **Not** HMRC, which reads the HMRC creditor's `creditor_call_completed` |
| `self_employed_since` | ISO `YYYY-MM-DD` / null | Date the client's current self-employment started | `null` (self-employed cases are flagged to confirm) | Self-employed call-sheet rule: required when 12+ months before `assessment_date` |
| `iva_term_months` | int, `60` or `72` | Proposed IVA term. **Already read.** | `60` | The existing dividend estimate only. **Not** the council DIV calculation, which takes its term from the mortgage (see below) |
| `monthly_di` | number | Monthly disposable income. **Already read.** | `financial_summary.net_balance` | Council DIV calculation ("Actual DI") |

### Per-creditor fields (`creditors[i]`)

| Field | Type | Meaning | Default if missing | Will be used by |
|-------|------|---------|--------------------|-----------------|
| `has_pod` | bool / null | Proof of debt is on file for this creditor | `null` | Debt-level-evidenced rule; POD over £500 rule; council tax POD for non-voting councils |
| `creditor_call_completed` | bool / null | A creditor call has been made and recorded (call sheet) for this creditor | `null` | Mortgage / rent / HP arrears rule; council tax call sheet for accepting / rejecting / DIV councils |
| `in_arrears` | bool / null | This mortgage or hire purchase account is in arrears (from its matched credit-report account) | `null` → the arrears rule flags the account to confirm, never returns the case | Arrears rule: a mortgage or HP creditor needs the call only when in arrears. Rent creditors always do |
| `div_returned` | decimal / null, e.g. `0.25` for 25% | Minimum dividend the council has returned for this case. **Decimal, not a percentage or pence.** | `null` → the engine uses the council's stored `CouncilRule.min_dividend_pence ÷ 100` | Council DIV calculation |
| `original_creditor` | string / null | The original lender behind a CCJ | `null` → the engine falls back to the existing `linked_creditor` | CCJ-majority rule |

### Rules these fields feed

| Proposed rule id | Applies when | Passes when | Otherwise |
|------------------|--------------|-------------|-----------|
| `COUNCIL-DIV-REQUIRED-DI` | Council debt is **over 50%** of unsecured debt **and** a DIV is known | `monthly_di` ≥ Required DI | Return the case: `threshold` = Required DI, `actual_value` = Actual DI, the message states all three |
| `DEBT-LEVEL-EVIDENCED` | Always | Evidenced unsecured debt ≥ £6,000 | Return the case |
| `POD-OVER-500` | A creditor balance is over £500 | `has_pod` is `true` | Flag only, provided `DEBT-LEVEL-EVIDENCED` passes (the case can go to drafting) |
| `HMRC-CALL-SHEET` | HMRC is a creditor | Every HMRC creditor has `creditor_call_completed: true` (the call to HMRC, on CAT's call sheet) | Return the case |
| `SELF-EMPLOYED-CALL-SHEET` | Self-employed for 12 months or more | `has_call_sheet` is `true` | Return the case |
| `COUNCIL-TAX-EVIDENCE` | A council tax creditor | Non-voting council: `has_pod`. Accepting / rejecting / DIV council: `creditor_call_completed` | Return the case; required **before SIP** |
| `ARREARS-CREDITOR-CALL` | A rent creditor, or a mortgage / HP creditor with `in_arrears: true` (`null` only flags) | `creditor_call_completed` is `true` | Return the case |
| `CCJ-ORIGINAL-CREDITOR` | CCJs make up the majority of the debt | Every CCJ has `original_creditor` (or `linked_creditor`) | Return the case |

**Council DIV formula (built, `_council_div_required_di`, migration 0095):**
`Required DI = ((Debt Level × DIV) + fee) ÷ term`.

* **Debt Level** — total unsecured debt.
* **DIV** — the creditor's `div_returned`, else the council's stored `min_dividend_pence ÷ 100`;
  the highest when several councils have one.
* **fee** — the rule's `GlobalCriteria.threshold_value` (seeded £4,250), so it changes without a release.
* **term** — 72 months when the client has a mortgage, else 60 (WATCH-22.2's test). CAT's
  `iva_term_months` is not used.

Worked example: £20,000 debt, 25% DIV, no mortgage → (5,000 + 4,250) ÷ 60 = **£154.17**. With an
actual DI of £150.00 the shortfall is £4.17 and the case is returned. Once the rule applies to a case,
the older `DIVIDEND-BELOW-MIN` flag is no longer raised for councils (it estimated without the fee).

The debt-type matcher reads "rent" as a word (`helpers.normalise_debt_type`): Aryza's
`current_account` used to count as rent.

### Rollout

1. The engine reads these fields; nothing changes for existing cases.
2. `COUNCIL-DIV-REQUIRED-DI` goes live first. It works before CAT changes anything because it falls
   back to the stored council DIV.
3. Every evidence rule ships **switched off** (`GlobalCriteria.is_active = False`). Each one is
   switched on only once CAT is sending its field, so cases are not flagged for evidence CAT cannot
   send yet.
4. **Done (Phase 4):** every result in `hard_blocks` / `flags` / `info` / `passed` now carries
   `required_before: "drafting" | "sip"`, so CAT knows which stage to block. It is `"drafting"`
   (block now) for every rule except `COUNCIL-TAX-EVIDENCE`, which is `"sip"` when everything it
   found is a council call sheet, and `"drafting"` if any council is missing a POD or is not in
   the council criteria list. The engine does not know the case stage itself; CAT enforces it.
   **CAT's decision (October 2026): every result, `"sip"` included, blocks at Send to Manager** —
   CAT's first forward gate — so CAT does not read `required_before` today.

### Open decisions (manager)

These must be answered before the engine rules are built:

1. **Council majority threshold.** The engine's `council_is_majority` is currently > 25% (a blocking
   minority). "Majority" normally means > 50%. Which applies to the DIV rule?
2. **Councils requiring DIV.** Is it any council with a stored minimum dividend, or only
   "Will Consider" councils? "Will Consider" and "Conditional Voter" councils with no DIV are not
   covered by the requirement as written.
3. **Debt Level in the DIV formula.** Total unsecured debt, or evidenced debt only?
4. **Several councils with a DIV.** Use the highest DIV?
5. **Hire purchase.** Is a call needed for every HP creditor, or only where there are arrears
   (`vehicle_arrears_months > 0`)?
6. **Existing dividend flag.** `COUNCIL-DIVIDEND-BELOW-MIN` estimates the dividend without the £4,250
   fee and only flags. Should it be retired for councils the new DIV rule covers?

### Open decisions (CAT team)

1. Confirm the field names and types above, or propose alternatives.
2. **HMRC call sheet:** is it a single client-level call sheet (`has_call_sheet`), or a call sheet
   against the HMRC creditor (`creditor_call_completed` on that creditor)?
3. **Council tax call sheet:** confirm it is recorded per council creditor (`creditor_call_completed`).
4. Can CAT always send `iva_term_months` as 60 or 72?
