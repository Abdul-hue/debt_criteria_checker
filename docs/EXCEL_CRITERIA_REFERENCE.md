# TIP CRITERIA & VOTING HISTORY — Rules Reference

Source of truth: `TIP CRITERIA & VOTING HISTORY.xlsx` (dated copies and the update procedure live in `docs/criteria-source/`; the markdown the app reads is generated from the workbook by `manage.py export_excel_criteria`).
All rules implemented in `debt_app/criteria_engine.py` must match this document exactly.

Last workbook update: **2026-10-12**. Evolve was retired, three Watch rules were removed and the HMRC equity rule moved to a 100% house valuation; see the sections below.

---

## Sheet: TIG Criteria

Rules applied by TIG (The Insolvency Group) before accepting a case into an IVA.

### Debt Thresholds
| Rule | Value | Note |
|------|-------|------|
| Minimum unsecured debt | £6,000 | Hard block — cases below this are not viable |
| Minimum disposable income (DI) | £100/month | Hard block — below this IVA is unsustainable |

### Income Evidence Requirements
These are evidence flags, not hard blocks, but caseworkers must collect before proposing:
- **Employed**: Last 3 wage slips
- **Benefits**: Benefit award letters
- **Universal Credit**: UC journal screenshot
- **Self-employed**: Most recent tax return + last 3 months business banking
- **CIS (Construction Industry Scheme)**: CIS invoices accepted in place of payslips

### Bank Statement Rules
- Client must provide recent bank statements to support I&E
- Gambling transactions must be identified and flagged

### Gambling Rules
- Total gambling spend must be **under £1,000** (hard block if over)
- If gambling spend is over £200, client must be registered with **GAMSTOP**
- Note: GAMSTOP registration is a mitigation, not a pass — caseworker review required

### HMRC Rules (8 hard rules)
HMRC debts are treated differently from commercial creditors:
1. HMRC debt included in IVA requires HMRC's agreement — never assume they'll vote yes
2. Self-assessment arrears: client must be up to date with filing (not just payment)
3. VAT arrears: trading must have ceased or arrangement in place
4. PAYE arrears: employer obligations must be current
5. Tax credits overpayments: treated as priority debt — check if DWP is recovering already
6. National Insurance: check if Class 2/4 are included or separate
7. HMRC rarely accepts IVAs with ongoing trading — seek specific confirmation
8. Antecedent transactions to HMRC (e.g., preference payments) are a hard reject
9. Equity: HMRC will reject if the client's property equity exceeds the HMRC debt, with the property valued at **100%** (not the 85% used by every other equity check). Confirmed by the sheet owner 2026-10-12 as HMRC-only. Engine rule TIG-15.4.

### Council Majority Rules
- A council creditor can swing the 75% majority — always assess council votes first
- If councils are likely to vote NO and represent >25% of debt by value, IVA will fail

### Recent Spend Rules
- **General**: No unusual or luxury spend in the last month that isn't explained
- **Monthly salary equivalent**: If client spent their entire salary in the last 2 months on non-essentials → hard flag

### Shop Direct Rules
- Purchases in the last **3 months**: reject if spend on non-essentials
- Purchases in the last **4 months**: flag for review
- Transactions sourced from `gold_transactions[]` only — never CRM balance fields
- Account must be at least a certain age (see creditor criteria)

### Creation Financial Rules
- Purchases in the last **4 months**: flag/reject
- No trial/introductory periods — must be a substantive account
- Transactions sourced from `gold_transactions[]` only

### Link Financial Rules
- Asset Link Capital and Link Financial treated as separate entities
- See `helpers.py:is_asset_link_capital()` and `is_link_financial()`

---

## Sheet: Watch Criteria (WPM)

Rules applied by WATCH (WPM) when voting on an IVA proposal. WATCH is a creditor representative.

### Hard Reject Rules
| Rule | Trigger | Note |
|------|---------|------|
| 6-year payoff | IVA term would require >6 years to repay | Not viable — bankruptcy may pay more |
| Antecedent transactions | Any preferential payments in look-back period | Hard reject — potential clawback |
| Car finance last 3 months | New HP/finance taken in last 3 months | Treat as recent spend; reject |

### Voting Conditions
| Rule | Trigger | Note |
|------|---------|------|
| Single-lender rule | WATCH is the only creditor or all others are <£500 | Reject — no benefit of IVA over DMP |
| IVA previously proposed | Prior IVA on record | Must be consistent — any inconsistency = reject |
| Gambling as main cause | Gambling identified as primary cause of debt | Require 3 months clean bank statements |

### Flags (not hard rejects, but affect proposal)
| Rule | Trigger | Note |
|------|---------|------|
| Children over 13 | Any child in household aged 13+ | Add sustainability paragraph to proposal |
| Age 80+ | Client is 80 or older | WATCH will abstain (do not vote) |
| Car value >£9k | Client vehicle valued over £9,000 | Downgrade to lower solution or require equity |
| HP payments >£400/month | Hire purchase payments exceed £400/month | Flag for modification clause |

### Removed 2026-10-12
Taken out of the workbook and confirmed by the sheet owner as no longer used. The rule switches are turned off through the criteria change workflow; the code stays so a rollback is possible.

| Former rule | Engine rule |
|-------------|-------------|
| Bankruptcy dividend higher than IVA dividend | WATCH-22.3 (was already off: the payload never carried a bankruptcy return) |
| Equity exceeds debt (85% LTV) | WATCH-22.4 |
| Any spending within 3 months | WATCH-22.6 |

The general equity check (TIG-16) is for non-WPM cases only, as the TIG sheet says, so WATCH cases now have no equity check. That is intended.

---

## Sheet: TIX Criteria

Rules applied by TIX when voting on an IVA proposal. TIX is a creditor representative (deregistered some creditors 30/06/2023).

### Creditor-Specific Spend Rules
| Creditor | Rule | Source |
|----------|------|--------|
| Shop Direct | Purchases in last 3 months = reject; account must be ≥6 months old | `gold_transactions[]` |
| Creation Financial | Purchases in last 4 months = reject | `gold_transactions[]` |

### Vehicle Finance Rules
- HP payments >£250/month → flag / modify clause required

### Deregistered Creditors (from 30/06/2023)
These creditors left TIX representation on 30/06/2023 and must not be marked as TIX after that date:
- UKAR
- Whistletree
- Computershare (mortgage services)
- Landmark Mortgages

Date-gating is implemented in `detect_representatives()`.

---

## Sheet: Evolve Criteria (retired 2026-10-12)

The sheet was removed from the workbook and the sheet owner confirmed "Evolve don't exist anymore". Evolve is no longer a creditor representative: its rules (EVOLVE-01 equity at 85% LTV, EVOLVE-02 single lender, EVOLVE-03 vulnerability evidence) are switched off through the criteria change workflow, the EVOLVE section is no longer exported to `Which_Representative_Criteria.md`, and the creditors that were mapped to it (Mint, NatWest, Octopus Energy, Shell Energy, TSB, Ulster Bank, Updraft and others) move to no representative. The code stays so a rollback is possible.

---

## Sheet: Dividends

Minimum dividend requirements (pence per £1) for specific creditors. If the estimated IVA dividend is below this, the creditor will reject.

| Creditor | Min Dividend | Additional Conditions |
|----------|--------------|-----------------------|
| Amigo Loans | DO NOT REQUIRE | No minimum — they accept any dividend |
| Asset Link Capital | 50p | |
| Believe Housing | 40p | |
| Beyond Housing | 30p | |
| Buckinghamshire Council | 50p | |
| Cardiff Credit Union | 45p | |
| Chorley Council | 30p | |
| Clockwise Credit Union | 50p | Account must be ≥2 months old |
| Colchester Council | 45p | |
| East Suffolk Council | 50p | |
| FCE Bank (Ford Credit) | 75p | High threshold — very selective |
| Funding Circle | 30p | |
| Funding Corp | 50p | |
| Glenside Finance | 25p | |
| Guarantor My Loan | 100p (was 50p until 2026-10-12) | |
| Hull & East Yorkshire Credit Union | 60p | |
| Medway Council | 25p minimum | Subject to review |
| Ratesetter | 25p | If account >6 months old; 50p if <6 months old |
| Reading Council | 60p | |
| Shell Energy | (none) | Workbook still says "evolve criteria", but Evolve was retired 2026-10-12 |
| South East Water | 40p | |
| Specialist Motor Finance | 50p | |
| Transave Credit Union | 60p | Account must be ≥3 months old |
| Wandsworth Council | 40p | |
| Worcester Council | 75p | Very high threshold |
| Wyre Forest Council | 50p | Reject if AOE (Attachment of Earnings) in place |

**Note:** Dividend thresholds are stored in `CreditorCriteria.min_dividend_pence` and `CouncilRule.min_dividend_pence`. The engine checks these in `_compute_dividend_analysis()`.

---

## Sheet: Which Representative

Assigns each creditor to a representative body (WATCH/TIX/EVERYDAY LOANS; EVOLVE until 2026-10-12). Used by `detect_representatives()` with date-gating.

### WATCH (WPM) Creditors (selection of key ones)
- Monzo — WATCH from **30/04/2024** (date-gated)
- La Redoute — WATCH from **16/07/2025** (date-gated)
- Scottish Power — added to the WATCH list 2026-10-12 (its General Creditor stance moved from DO NOT VOTE to Accept, "see Watch criteria")
- Most high-street banks and major card issuers

### TIX Creditors
- Shop Direct / Very / Littlewoods / JD Williams (catalogue)
- Creation Financial
- UKAR / Whistletree / Computershare / Landmark — **deregistered 30/06/2023**

### EVOLVE Creditors (retired 2026-10-12)
- No longer exported. See "Sheet: Evolve Criteria" above.

### EVERYDAY LOANS Creditors
- Everyday Loans (standalone representative)

### NONE
- Creditors not represented by any of the above bodies vote independently

**Implementation note:** Representatives are stored in `CreditorCriteria.representative` and detected by `detect_representatives()` in the engine, which applies date-gating using `assessment_date`.

---

## Sheet: GENERAL CREDITOR

Voting behaviour for ~200+ individual creditors. Key statuses:

| Status | Meaning |
|--------|---------|
| ACCEPT | Creditor will vote yes on a conforming IVA |
| REJECT | Creditor will vote no — do not include in IVA without specific reason |
| WILL_CONSIDER | Creditor votes case-by-case — check conditions |
| DO_NOT_VOTE | Creditor submits proof of debt but does not vote |
| CONDITIONAL_VOTER | Creditor votes only if dividend meets their threshold |

### Key Individual Creditor Rules

**TBI (Debt collections)**
- `blocked_until_cleared = True` — do not propose until TBI is resolved

**Moneybarn (vehicle finance)**
- `vehicle_arrears_repossession_months = 2` — if client is 2+ months behind, repossession risk → flag
- `fees_cap_percentage = 25` — IP fees capped at 25% of realisations for this creditor

**Bamboo Loans**
- `reject_if_never_made_payment = True` — if client has never made a payment to Bamboo, they will reject

**Admiral Loans** (workbook 2026-10-12)
- `account_age_months = 6` (was 3) — "running cases: 6 months or older"
- `reject_if_second_iva = True` — "REJECT IF PREVIOUS IVA"; the engine's flag fires on any previous IVA

**Loans by Mal** (workbook 2026-10-12)
- `account_age_months = 3` — under 3 months is a reject
- `young_account_months = 6`, `young_account_min_dividend_pence = 40` — "if under 6 months but older than 3 months - has to 40p/£". These two fields are new: when both are set, an account younger than `young_account_months` must meet the higher dividend (exactly that many months old counts as not younger); an unknown account age is flagged (`CREDITOR-YOUNG-ACCOUNT-DIV-UNVERIFIED`) and checked against the standard minimum, never assumed young.

**Ratesetter** (confirmed 2026-10-13)
- `min_dividend_pence = 25`, `young_account_months = 6`, `young_account_min_dividend_pence = 50` — "25p; if under 6 months old it 50p". Exactly six months old is the standard 25p.
- `account_age_months = None` — the previous 6-month reject was a stand-in for the 50p tier and contradicted the sheet (a young loan needs 50p, it is not refused). Proposed through the change workflow alongside the tier.

**HM Revenue & Customs** (property valuation, confirmed 2026-10-12)
- TIG-15.4 compares available equity at **100%** of the property value (`property_value - mortgage_balance`) with the HMRC balance. A property with a mortgage but no recorded valuation reaches the engine as "value unknown" (not £0), so the rule reports "could not be completed" instead of passing silently (pipeline fix 2026-10-13).
- The row's `reject_if_equity_exceeds_debt` flag was the generic per-creditor check at 85% against total unsecured debt. The sheet owner decided (2026-10-13) it is superseded: the HMRC draft switches it off in the same request that switches TIG-15.4 on, and the seeder no longer sets it. Other equity rules that remain: TIG-16 (general flag, non-WPM cases only, not HMRC-specific), WATCH-22.4 and EVOLVE-01 (both being switched off). Aryza sends the name "HMRC". Since 2026-10-13 it is an alias of the "HM Revenue & Customs" row, on the workbook's own evidence (GENERAL CREDITOR row 174 is "HM Revenue & Customs" and its notes call the creditor "HMRC"; the TIG sheet states the HMRC rules under "HMRC"). Those cases now take the row's Will Consider stance and its notes flag instead of resolving as unknown; "HMRC - benefits overpayments" is a separate row and is not matched. TIG-15.x rules match by name and are unaffected.

### Unconfirmed stance (`status = UNKNOWN`, added 2026-10-13)
A creditor whose stance the sheet owner has not confirmed is stored with status UNKNOWN. The engine reports "no recorded standing position", flags `CREDITOR-STANCE-UNCONFIRMED`, and never counts it as an acceptance; the majority logic treats it as a vote that could go either way. Used for:
- the seven creditors that lost the retired Evolve representative and appear nowhere else in the workbook: Mint, NatWest, NatWest Bank, Royal Bank of Scotland, The Royal Bank of Scotland Plc, TSB Bank, Ulster Bank. (Octopus Energy and Updraft keep the General sheet's Accept. Shell Energy keeps Accept: the user confirmed on 2026-10-13 that it is the sheet's "Shell Energy Retail Limited (NOW OCTOPUS)" row; the draft deactivates that duplicate row (kept, not deleted). Note that "Shell Energy Retail Limited" as a raw name resolves to Octopus Energy, whose trading names migration 0030 seeded with it (the sheet says "NOW OCTOPUS"); both records are Accept, so the outcome is the same either way. Barclaycard moves to WATCH, where the Which Representative sheet lists it.)
- Zilch (buy-now-pay-later), which appears on real cases but not in the workbook: a row exists for name matching only (aliases `zilch`, `zilch technology`; trading names Zilch Technology Limited / LTD) until the sheet owner gives a stance.
Do not run `fix_unknown_creditor_statuses`: its Rule 1 converts UNKNOWN to ACCEPT for represented rows, which is exactly the default this status exists to prevent.

**Commsave Credit Union**
- Special voting behaviour — check notes in seed data

**Buddy Loans**
- Guarantor product — check `requires_pg_called_up` / `guarantee_called_up` flags

**Everyday Loans**
- Has its own representative arrangement — stored separately

**Royal Mail / Penny Post Credit Union**
- If client is a Royal Mail employee, flag Penny Post CU information
- Some creditors reject police officers — check `reject_if_police_employed` flag

### Conditional Voters
Some creditors are `CONDITIONAL_VOTER` — they only vote yes if the dividend meets `conditional_voter_min_dividend_pence`. The engine checks this in `_check_conditional_voters()`.

### Arrangement Call Required
Some creditors require a pre-proposal call before the IVA can be sent:
- `requires_arrangement_call_before_proposing = True`
- Engine flags this in `_check_creditor_individual()` → `CREDITOR-ARRANGEMENT-CALL`

---

## Sheet: Councils

Voting behaviour for ~300+ individual councils. Key distinctions from general creditors:

### Debt Types
Councils can have different votes per debt type:
| Debt Type | Model Field | Note |
|-----------|-------------|------|
| Council Tax | `COUNCIL_TAX` | Primary council debt |
| Parking Charge Notice | `PCN` | Often Do Not Vote |
| Housing Benefit Overpayment | `HOUSING_BENEFIT` | DWP may already be recovering |

Per-debt-type overrides are stored in `DebtTypeCouncilVote` model.

### Reject Conditions (CouncilRule flags)
| Flag | Trigger | Example Council |
|------|---------|-----------------|
| `reject_if_employed` | Client is employed | Mid Suffolk (reject employed, accept unemployed) |
| `reject_if_unemployed_and_homeowner` | Client is unemployed AND owns property | Various |
| `reject_if_benefits_only` | Income is solely benefits | Huntingdonshire |
| `reject_if_any_benefits` | Client receives any benefits at all | Huntingdonshire |
| `reject_if_previous_iva` | Client has a prior IVA | Huntingdonshire |
| `reject_if_dro_criteria_met` | Client would qualify for a DRO | Huntingdonshire |
| `reject_if_aoe_in_place` | Attachment of Earnings in place | Wyre Forest, Huntingdonshire |
| `reject_if_joint_one_party_only` | Joint debt, only one party in IVA | Various |
| `reject_if_joint_both_parties` | Joint IVA proposed | Various |
| `reject_if_sole` | Sole IVA (not joint) | Shropshire Council |
| `reject_if_joint_one_employed` | Joint case, at least one party employed | Huntingdonshire |

### Conditional Rejection Logic
When a council has ANY `reject_if_*` flag set, but NONE of them are triggered by the case data:
- **Effective status = ACCEPT** (not the base WILL_CONSIDER)
- This reflects the Excel note pattern: "ACCEPT IF [condition] — REJECT IF [other condition]"
- Implemented as `_has_conditional_reject` in `_check_council_rules()`

### Special Flags
| Flag | Meaning |
|------|---------|
| `do_not_chase` | Do not contact this council proactively — they will reject if chased; note for caseworker |
| `include_current_year_ct` | Include the current (not-yet-billed) year's council tax in the IVA proposal |

**`include_current_year_ct` councils:** Cardiff Council, Walsall Council, Waltham Forest Council

### Slough Council
- Status: REJECT — will not participate in IVAs

### Shropshire Council
- `reject_if_sole = True` — sole IVA applications are rejected
- If debt is joint but only one party in IVA: POD only (proof of debt submitted, no vote)

### Huntingdonshire Council (comprehensive conditions)
All of the following trigger rejection:
- `reject_if_benefits_only`
- `reject_if_any_benefits`
- `reject_if_joint_one_employed`
- `reject_if_previous_iva`
- `reject_if_dro_criteria_met`
- `reject_if_aoe_in_place`

---

## Sheet: County Councils

Some council tax debts are billed by county councils that route the IVA vote to a specific district council. The `CountyCouncilRouting` model maps `(county_name, district_name)` to a `CouncilRule`.

### Key County Council Routings (24 entries)
- Buckinghamshire County Council → routes to relevant district
- Other shire counties similarly route to district councils

**Implementation note:** When a creditor is named as a county council (e.g. "Buckinghamshire"), `_check_council_rules()` will not find a `CouncilRule` row for it directly — the routing is resolved upstream in `_phase4_county_council()`. County council names appearing in the creditors list are skipped by `_check_council_rules()` (no row → `continue`).

---

## Engine Implementation Cross-Reference

| Sheet | Engine Function | Model |
|-------|----------------|-------|
| TIG Criteria | `assess_case()` TIG rule block | `GlobalCriteria` |
| Watch Criteria | `assess_case()` WATCH rule block | `GlobalCriteria`, `CreditorCriteria` |
| TIX Criteria | Recent spend checks, `_check_shop_direct()` | `CreditorCriteria` |
| Evolve Criteria (retired 2026-10-12) | `assess_case()` EVOLVE rule block, switched off | `GlobalCriteria` |
| Dividends | `_compute_dividend_analysis()` | `CreditorCriteria.min_dividend_pence`, `CouncilRule.min_dividend_pence` |
| Which Representative | `detect_representatives()` | `CreditorCriteria.representative` |
| GENERAL CREDITOR | `_check_creditor_individual()` | `CreditorCriteria` (all flags) |
| Councils | `_check_council_rules()` | `CouncilRule`, `DebtTypeCouncilVote` |
| County Councils | `_phase4_county_council()` | `CountyCouncilRouting` |

---

## Rule Code Reference

Rule codes emitted in `findings[].code`:

| Code | Source | Meaning |
|------|--------|---------|
| `CREDITOR-BLOCKED` | `_check_creditor_individual` | TBI or other blocked creditor — do not propose |
| `CREDITOR-NO-PAYMENT` | `_check_creditor_individual` | Client never made a payment to this creditor |
| `CREDITOR-REPOSSESSION-RISK` | `_check_creditor_individual` | Vehicle arrears threshold exceeded or asset still held |
| `CREDITOR-ARRANGEMENT-CALL` | `_check_creditor_individual` | Pre-proposal call required, not yet confirmed |
| `CREDITOR-FEES-CAP` | `_check_creditor_individual` | IP fees capped — note for caseworker |
| `CREDITOR-UNKNOWN` | `_check_creditor_individual` | No criteria row for this creditor — manual review |
| `COUNCIL-SOLE-REJECT` | `_check_council_rules` | Council rejects sole IVA applications |
| `COUNCIL-SOLE-POD-ONLY` | `_check_council_rules` | Joint debt, sole IVA — POD only, no vote |
| `COUNCIL-TRIGGER-EMPLOYED` | `_check_council_rules` | Council rejects employed clients |
| `COUNCIL-TRIGGER-BENEFITS-ONLY` | `_check_council_rules` | Council rejects benefits-only income |
| `COUNCIL-TRIGGER-ANY-BENEFITS` | `_check_council_rules` | Council rejects any benefits received |
| `COUNCIL-TRIGGER-PREVIOUS-IVA` | `_check_council_rules` | Council rejects prior IVA history |
| `COUNCIL-TRIGGER-DRO-CRITERIA` | `_check_council_rules` | Council rejects DRO-eligible clients |
| `COUNCIL-TRIGGER-AOE-IN-PLACE` | `_check_council_rules` | Council rejects if AOE already in place |
| `COUNCIL-TRIGGER-JOINT-ONE-EMPLOYED` | `_check_council_rules` | Council rejects joint IVA where one party is employed |
| `INFO-DO-NOT-CHASE` | `_check_council_rules` | Informational — do not contact this council |
| `INFO-INCLUDE-CURRENT-YEAR-CT` | `_check_council_rules` | Informational — include current year CT in proposal |
| `INFO-MIN-DIVIDEND` | `_check_council_rules` | Informational — minimum dividend threshold noted |
