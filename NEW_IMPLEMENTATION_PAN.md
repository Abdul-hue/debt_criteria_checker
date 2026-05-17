IVA Criteria Checker — Full Implementation Plan
Architecture overview
The system is a multi-phase rule engine API. A case payload comes in, flows through ordered checker modules, and returns a structured result with flags per creditor, per council, and globally.
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation-duration: 0.25s;
    animation-timing-function: cubic-bezier(0.19, 1, 0.22, 1);
  }
VvisualizeVvisualize show_widget
Database schema
Core tables
creditor_rules — one row per creditor
sqlCREATE TABLE creditor_rules (
  id                                    SERIAL PRIMARY KEY,
  creditor_name                         VARCHAR(200) NOT NULL,
  status                                VARCHAR(50) NOT NULL,
  -- status values: ACCEPT, REJECT, WILL_CONSIDER, DO_NOT_VOTE, CONDITIONAL_VOTER
  representative                        VARCHAR(50),  -- TIX, WPM, EVOLVE, DIRECT
  min_dividend_pence                    INT,
  min_debt_age_weeks                    INT,
  min_debt_age_months                   INT,
  max_debt_age_months                   INT,
  reject_if_recent_spend_months         INT,
  reject_if_equity_exceeds_debt         BOOLEAN DEFAULT FALSE,
  reject_if_in_dmp                      BOOLEAN DEFAULT FALSE,
  reject_if_never_made_payment          BOOLEAN DEFAULT FALSE,
  reject_if_ie_doesnt_match_application BOOLEAN DEFAULT FALSE,
  reject_if_debt_repayable_within_months INT,
  reject_if_client_still_has_asset      BOOLEAN DEFAULT FALSE,
  reject_if_majority_share_exceeds_pct  DECIMAL(5,2),
  reject_if_second_iva                  BOOLEAN DEFAULT FALSE,
  reject_if_police_employed             BOOLEAN DEFAULT FALSE,
  reject_if_taken_fraudulently          BOOLEAN DEFAULT FALSE,
  reject_if_client_still_with_them      BOOLEAN DEFAULT FALSE,
  requires_pg_called_up                 BOOLEAN DEFAULT FALSE,
  requires_arrangement_call_before_proposing BOOLEAN DEFAULT FALSE,
  requires_grant_overpayment_only       BOOLEAN DEFAULT FALSE,
  vehicle_arrears_repossession_months   INT,
  fees_cap_percentage                   DECIMAL(5,2),
  termination_risk_if_vehicle_on_finance BOOLEAN DEFAULT FALSE,
  conditional_voter                     BOOLEAN DEFAULT FALSE,
  conditional_voter_min_dividend_pence  INT,
  open_banking_access                   BOOLEAN DEFAULT FALSE,
  min_di_for_fees_pence                 INT,
  fraud_claim_risk                      BOOLEAN DEFAULT FALSE,
  blocked_until_cleared                 BOOLEAN DEFAULT FALSE,
  blocked_reason                        TEXT,
  effective_from                        DATE,
  last_updated                          TIMESTAMP DEFAULT NOW(),
  notes                                 TEXT
);
council_rules — one row per council
sqlCREATE TABLE council_rules (
  id                                    SERIAL PRIMARY KEY,
  council_name                          VARCHAR(200) NOT NULL,
  status                                VARCHAR(50) NOT NULL,
  min_dividend_pence                    INT,
  reject_if_employed                    BOOLEAN DEFAULT FALSE,
  reject_if_aoe_in_place                BOOLEAN DEFAULT FALSE,
  reject_if_aoe_possible                BOOLEAN DEFAULT FALSE,
  reject_if_benefit_only                BOOLEAN DEFAULT FALSE,
  reject_if_benefits_except_child_benefit BOOLEAN DEFAULT FALSE,
  reject_if_dro_eligible                BOOLEAN DEFAULT FALSE,
  reject_if_second_iva                  BOOLEAN DEFAULT FALSE,
  reject_if_previous_iva_failed         BOOLEAN DEFAULT FALSE,
  reject_if_public_funds_policy         BOOLEAN DEFAULT FALSE,
  pod_only_if_joint_sole_iva            BOOLEAN DEFAULT FALSE,
  reject_if_joint_sole_iva              BOOLEAN DEFAULT FALSE,
  charging_order_risk_if_property_owner BOOLEAN DEFAULT FALSE,
  includes_current_year_ct_regardless   BOOLEAN DEFAULT FALSE,
  chase_triggers_rejection              BOOLEAN DEFAULT FALSE,
  aoe_theoretical_triggers_reject       BOOLEAN DEFAULT FALSE,
  reject_if_employed_income_below_monthly INT,
  effective_from                        DATE,
  last_updated                          TIMESTAMP DEFAULT NOW(),
  notes                                 TEXT
);
county_council_routing — maps county councils to their district councils
sqlCREATE TABLE county_council_routing (
  id                    SERIAL PRIMARY KEY,
  county_name           VARCHAR(200) NOT NULL,
  district_name         VARCHAR(200) NOT NULL,
  district_council_id   INT REFERENCES council_rules(id),
  contact_number        VARCHAR(100),
  notes                 TEXT
);
conditional_voter_rules — creditors who vote only when their vote is decisive
sqlCREATE TABLE conditional_voter_rules (
  id                    SERIAL PRIMARY KEY,
  creditor_name         VARCHAR(200) NOT NULL,
  default_behaviour     VARCHAR(50) DEFAULT 'DO_NOT_VOTE',
  votes_if_required     BOOLEAN DEFAULT TRUE,
  min_dividend_pence    INT NOT NULL,
  contact_required_flag BOOLEAN DEFAULT TRUE,
  notes                 TEXT
);
-- Seed:
-- Buddy Loans t/a Advancis Ltd: min 50p, contact required
-- Salary Finance: no min div specified, must be notified if vote needed
-- PRA Group: pod after approval only, will never help achieve majority (NOT a conditional voter)
debt_type_council_votes — councils that vote differently by debt type
sqlCREATE TABLE debt_type_council_votes (
  id           SERIAL PRIMARY KEY,
  council_name VARCHAR(200) NOT NULL,
  debt_type    VARCHAR(100) NOT NULL,
  -- debt_type values: COUNCIL_TAX, HOUSING_BENEFIT, PCN, CARE_COSTS, RENT_ARREARS
  status       VARCHAR(50) NOT NULL,
  notes        TEXT
);
-- Seed:
-- Southwark: PCN=ACCEPT, COUNCIL_TAX=REJECT
-- Lewisham: COUNCIL_TAX=REJECT, PCN=DO_NOT_VOTE
-- Durham: HOUSING_BENEFIT=DO_NOT_VOTE, COUNCIL_TAX=REJECT
-- Portsmouth: PCN=DO_NOT_VOTE, COUNCIL_TAX=REJECT
-- Mid Suffolk: EMPLOYED=REJECT (via council_rules.reject_if_employed), UNEMPLOYED=ACCEPT
creditor_open_banking_rules — creditors with live bank access
sqlCREATE TABLE creditor_open_banking_rules (
  id                       SERIAL PRIMARY KEY,
  creditor_name            VARCHAR(200) NOT NULL,
  reviews_months           INT DEFAULT 6,
  ie_must_match_exactly    BOOLEAN DEFAULT FALSE,
  will_reject_if_mismatch  BOOLEAN DEFAULT TRUE,
  notes                    TEXT
);
-- Seed:
-- Fintern/Abound: 6 months, exact match required, no trials
-- Everyday Loans: 6 months, mismatch = reject
-- TM Advances: I&E must be identical, will never take majority case
-- Bamboo: compares I&E with loan application
representative_routing — maps creditors and sub-brands to their representative
sqlCREATE TABLE representative_routing (
  id               SERIAL PRIMARY KEY,
  creditor_name    VARCHAR(200) NOT NULL,
  brand_name       VARCHAR(200),
  representative   VARCHAR(50) NOT NULL,  -- TIX, WPM, EVOLVE, DIRECT
  effective_from   DATE NOT NULL,
  notes            TEXT
);
-- Critical seed note: all sub-brands must be included, not just top-level names.
-- Example: Barclaycard alone has 14 sub-brands (Argos Mastercard, BHS Mastercard,
-- Goldfish, Littlewoods, Morgan Stanley, Orange Credit Card, Sky Card, etc.)
-- La Redoute: effective_from = 2025-06-30, representative = WPM
-- Virgin Money (Loan): WPM
-- Thames Water: WPM from 06/04
-- Everyday Loans: always use current balance, not total payable

API request payload
json{
  "case_id": "TIG99999",
  "client": {
    "age": 42,
    "employment_status": "EMPLOYED",
    "income_sources": ["EMPLOYMENT"],
    "total_monthly_income": 2100,
    "disposable_income": 180,
    "is_homeowner": false,
    "property_equity": 0,
    "has_partner_on_case": false,
    "is_currently_in_dmp": false,
    "is_royal_mail_employee": false,
    "is_police_officer": false,
    "employer_name_normalised": "ABC Logistics",
    "vulnerabilities": [],
    "previous_iva": false,
    "previous_iva_failed": false
  },
  "vehicle": {
    "included_in_iva": false,
    "current_value": 0,
    "hp_balance": 0,
    "hp_monthly_payment": 0,
    "vehicle_arrears_months": 0,
    "vw_finance_exists": false,
    "finance_termination_risk": false
  },
  "debts": [
    {
      "creditor_name": "Moneybarn",
      "debt_type": "HP",
      "balance": 8500,
      "date_of_last_spend": "2024-08-01",
      "months_since_last_payment": 3,
      "first_payment_made": true,
      "payments_made_count": 12,
      "is_joint": false,
      "is_guarantor_loan": false,
      "guarantee_called_up": null,
      "arrangement_confirmed_before_proposing": false,
      "ie_matches_loan_application": null,
      "is_grant_overpayment": false,
      "client_still_customer": false,
      "client_still_has_asset_in_possession": false,
      "vehicle_arrears_months": 2,
      "open_banking_reviewed": false
    }
  ],
  "case_financials": {
    "total_debt": 24000,
    "proposed_monthly_payment": 180,
    "proposed_term_months": 60,
    "estimated_dividend_pence": 28,
    "total_return": 10800,
    "bankruptcy_dividend_comparison_pence": 12
  },
  "property": {
    "is_homeowner": false,
    "equity": 0,
    "mortgage_outstanding": 0
  }
}

Checker modules — detailed logic
Phase 1: Hard gates
GlobalEligibilityChecker

Total debt ≥ £6,000 → FAIL if under
Disposable income ≥ £100/month → FAIL if under
SFS compliance verified → FAIL if not
DLA/PIP offset applied where applicable

DmpStatusChecker

Reads client.is_currently_in_dmp
For each debt, checks creditor_rules.reject_if_in_dmp
If TRUE and client is in DMP → ERROR regardless of majority position
Affected creditors: Commsave Credit Union, CAMBRIAN Credit Union

CountyCouncilRouterChecker

For every council debt, check county_council_routing table
If the named council is a county council → resolve to correct district council before any CouncilRulesChecker runs
If district cannot be resolved → WARNING: "Council routing ambiguous — verify district"
All 15 counties from the source sheet must be seeded: Buckinghamshire, Cambridgeshire, Cumbria, Derbyshire, Devon, Dorset, East Sussex, Gloucestershire, Hampshire, Hertfordshire, Lancashire, Lincolnshire, Norfolk, North Yorkshire, Northamptonshire, Nottinghamshire, Oxfordshire, Somerset, Staffordshire, Suffolk, Warwickshire, West Sussex, Worcestershire

VehicleTerminationRiskChecker

Checks vehicle.vw_finance_exists AND whether VW Financial Services appears in debts
If TRUE → CRITICAL WARNING: "Proposing this IVA will cause Volkswagen Financial Services to terminate the client's current finance arrangement"
This is a pre-gate — runs before dividend calculations


Phase 2: Creditor & council rejection
CreditorIndividualChecker — all 22 new columns checked per creditor
Key rules by creditor from source data:
CreditorRuleColumnMoneybarnVehicle arrears ≥ 2 months = repossess regardlessvehicle_arrears_repossession_months = 2MoneybarnEmployed clients: fees capped at 25% of total returnfees_cap_percentage = 25MoneybarnIf arrears exist, arrangement call required before proposingrequires_arrangement_call_before_proposing = TRUETBI Financial ServicesREJECT ALL — DO NOT RUNstatus = REJECT, blocked_until_cleared = TRUE, blocked_reason = 'FCA complaint pending — Debra'Bamboo4 independent reject triggers: age < 3 months, never paid, repayable < 96 months, equityAll 4 checked independentlyBuddy LoansConditional voter — votes only if needed, 50p/£ minconditional_voter = TRUE, conditional_voter_min_dividend_pence = 50Salary FinanceConditional voter — must be notified if vote neededconditional_voter = TRUEAmigoCurrently in redress — status flag REDRESS_NOT_VOTINGstatus = DO_NOT_VOTE, notes = 'In redress July 2024 — monitor for change'Penny Post CURoyal Mail employees can EXCLUDE this debtLogic in SpecialEmployerCheckerPlata LoansReject if debt > 85% of total debt levelreject_if_majority_share_exceeds_pct = 85Commsave CUReject if > 50% of total debtreject_if_majority_share_exceeds_pct = 50Commsave CUReject if client in DMPreject_if_in_dmp = TRUECAMBRIAN CUReject if < 6 months old AND if client in DMPBoth checkedVW Financial ServicesWill terminate current finance arrangementtermination_risk_if_vehicle_on_finance = TRUENo1 Copperpot CUReject if client is police officerreject_if_police_employed = TRUEStudent Loans CompanyOnly consider grant overpayments, not loansrequires_grant_overpayment_only = TRUEWelsh WaterReject if previous IVA terminatedreject_if_second_iva = TRUELoans at HomeMust have made first paymentreject_if_never_made_payment = TRUEMr LenderMust chase for votestatus = ACCEPT, notes = 'Must chase — will not vote proactively'Motonovo FinanceHP car collected and sold post-IVA — flag riskWARNING in responseSnap on ToolsReject if client still has tools in possessionreject_if_client_still_has_asset = TRUESlough Council (creditor side)Chasing triggers rejectionchase_triggers_rejection = TRUE1st Plus 1 Loans (now Credit Labs)Change of circumstances must be evidenced; guarantor must confirmrequires_pg_called_up = TRUEUK Credit LtdMin DI £150 for fees; reject if < 6 monthsmin_di_for_fees_pence = 15000, min_debt_age_months = 6IWOCAPG must have been called up; equity checkrequires_pg_called_up = TRUE, reject_if_equity_exceeds_debt = TRUE
CouncilRulesChecker — 9 new columns checked per council
Key rules from source data:
CouncilRuleColumnHuntingdonshireReject if benefit only, any benefits, joint/one employed, previous IVA, DRO criteria met, AOE in place6 independent checksDoncasterReject if employed (AOE); reject if unemployed with property (charging order)reject_if_employed, charging_order_risk_if_property_ownerShropshireSole → reject; joint one party → pod only; joint both parties → reject unless 100ppod_only_if_joint_sole_iva, reject_if_joint_sole_ivaBuckinghamshireReject if employed (AOE possible); 50p/£ min divreject_if_employed, min_dividend_pence = 50GatesheadReject if employed; reject if previous IVA failedreject_if_employed, reject_if_previous_iva_failedOldhamReject second IVAreject_if_second_iva, reject_if_previous_iva_failedTelford & WrekinReject second IVA; reject if AOE possiblereject_if_second_iva, reject_if_aoe_possibleHerefordshireReject if previous IVA failedreject_if_previous_iva_failedReigate & BansteadIf joint, will not vote — just chase other partyreject_if_joint_sole_ivaCardiffAlways include current year CTincludes_current_year_ct_regardlessWalsallAlways include current year CTincludes_current_year_ct_regardlessWaltham ForestAlways bill full year CTincludes_current_year_ct_regardlessSloughChasing triggers rejectionchase_triggers_rejectionMid SussexReject if any benefits except child benefitreject_if_benefits_except_child_benefitRichmond Upon ThamesWill not include current year CT unless already paidSpecific note in notesWealdenReject if client meets DRO criteriareject_if_dro_eligibleWolverhamptonReject if employed income > £400/month (AOE applicable)reject_if_employed_income_below_monthly = 400
Colchester dividend conflict resolution rule:
The Dividends sheet says 45p/£; the Council sheet says 65p/£ confirmed July 2025. Rule: the record with the more recent last_updated timestamp takes precedence. Council sheet wins here. This resolution rule must be documented in the FlagEngine.
DebtTypeCouncilChecker

For each council debt, look up debt_type_council_votes using council_name + debt_type
If a row exists, use that status instead of council_rules.status
Examples: Southwark PCN debt → ACCEPT; Southwark council tax debt → REJECT

HMRCRulesChecker

Reject if deduction from income or benefits in place
Reject if self-employed with late submissions
Reject if equity > their debt
Reject if SEISS debt included (cannot be included at all)
Below £4k: HMRC does not vote — flag as INFO/WARN, not FAIL
Joint debt rule: if only one party in IVA, HMRC removes client's name and chases second party — flag as INFO


Phase 3: IP-specific gates
WPMRulesChecker — 13 criteria checked:

Debt repayable < 6 years
Bankruptcy dividend comparison
Equity vs debt comparison
Single lender check
3-month spend check
Children over 13 sustainability paragraph required
Age 80+ — abstain
Car value threshold
HP payment cap (£250/month)
Gambling cause
Antecedent transactions
Previously proposed IVA content match
Car finance in last 3 months

Each criterion that is overridden on vulnerability grounds must produce a VULNERABILITY_EVIDENCE_REQUIRED flag — not a silent pass.
TIXRulesChecker — 5 criteria:

Shop Direct spend window
Shop Direct account age
Creation spend window
HP cap at £250/month
UKAR/Whistletree/Computershare/Landmark — excluded from June 2023

Same vulnerability evidence flag requirement.
EvolveRulesChecker — 2 criteria:

LTV equity threshold ≤ 85%
Single-lender rule


Phase 4: Evidence & documentation
IEMatchChecker

For creditors with reject_if_ie_doesnt_match_application = TRUE or open_banking_access = TRUE
Checks debts[].ie_matches_loan_application
If false or null → ERROR: "I&E must match loan application for this creditor"
Affected: TM Advances, Loans by Mal, Bamboo, Guarantor My Loan

OpenBankingRiskChecker

For creditors in creditor_open_banking_rules
If open_banking_access = TRUE and match cannot be confirmed → ERROR
Note: Fintern/Abound has no trials — any mismatch = certain rejection


Phase 5: Financial analysis
DebtRepayabilityChecker

Per-creditor thresholds from source (all independent of each other):

Bamboo: reject if repayable < 96 months
Loans by Mal: reject if repayable < 84 months
Lifestyle Loans: reject if repayable < 80 months
Everyday Loans: reject if repayable < 120 months (10 years)
Hastings Direct: reject if repayable < 120 months (10 years — "prefer DMP due to fees")
Amigo (when active): reject if repayable < 84 months


Uses case_financials.total_debt ÷ monthly dividend to estimate repayment months


Phase 6: Special handlers
GuarantorRulesChecker

For creditors with requires_pg_called_up = TRUE
Checks debts[].guarantee_called_up
If null or false → WARNING: "Guarantor must be contacted before proposing — creditor requires confirmation"
Affected: 1st Plus 1 Loans (Credit Labs), IWOCA, UK Credit Ltd, Amigo (when active)

ConditionalVoterHandler

Runs after all voting positions aggregated
Checks if majority is achievable without conditional voters
If not → CONDITIONAL_VOTER_REQUIRED flag with contact instructions
Buddy Loans: contact required, 50p/£ min
Salary Finance: must notify them that vote is needed

SpecialEmployerChecker

client.is_royal_mail_employee + Penny Post Credit Union debt → EXCLUDE_DEBT
client.is_police_officer + No1 Copperpot Credit Union debt → REJECT with note about employment impact

VehicleTerminationRiskChecker (also fires here for detailed flag)

Generates CRITICAL WARNING with exact wording for case notes


Critical individual creditor seed data (high priority)
These must be seeded correctly before any other creditor — they are the highest-risk gaps:
TBI Financial Services:
  status = REJECT
  blocked_until_cleared = TRUE
  blocked_reason = 'FCA complaint lodged by Debra — do not run any cases until response received'
  notes = 'Bamboo debts sold to TBI post-approval — distorts voting behaviour. Flag any case with both Bamboo and TBI.'

Bamboo:
  status = REJECT
  Rejection triggers (ALL checked independently):
    - min_debt_age_months = 3 (reject if < 3 months at signing)
    - reject_if_never_made_payment = TRUE
    - reject_if_debt_repayable_within_months = 96
    - reject_if_equity_exceeds_debt = TRUE
  Modification behaviour: if I&E maxed, Bamboo modifies to fit inside 96 months — this is MOD not REJECT
  open_banking_access = TRUE

Moneybarn:
  status = ACCEPT
  vehicle_arrears_repossession_months = 2
  fees_cap_percentage = 25 (employed clients only)
  requires_arrangement_call_before_proposing = TRUE (if arrears present)
  notes = 'Car must have been returned and in Moneybarn possession — otherwise REJECT'

Volkswagen Financial Services:
  status = DO_NOT_VOTE
  termination_risk_if_vehicle_on_finance = TRUE
  notes = 'Will terminate current finance arrangement if car is on finance and IVA proposed'

Amigo:
  status = DO_NOT_VOTE
  notes = 'In redress as of July 2024 — not voting. When redress ends, multi-branch rule applies:
    - Repayable < 84 months → REJECT
    - > 12 months old + evidenced change of circs → consider at 30p/£
    - < 12 months old + evidenced change → 50p/£
    - No evidence → REJECT regardless of age
    - Previous IVA failed → REJECT
    - Same rules apply to guarantor'
  amigo_status_flag = REDRESS_NOT_VOTING  (toggleable when status changes)

API response structure
json{
  "case_id": "TIG99999",
  "overall_status": "FAIL",
  "flags": [
    {
      "type": "CRITICAL_WARNING",
      "module": "VehicleTerminationRiskChecker",
      "message": "Proposing this IVA will cause VW Financial Services to terminate the client's current finance arrangement.",
      "creditor": "Volkswagen Financial Services"
    },
    {
      "type": "ERROR",
      "module": "CreditorIndividualChecker",
      "message": "Moneybarn: vehicle has 2+ months arrears — repossession will occur regardless of IVA. Arrangement call required before proposing.",
      "creditor": "Moneybarn"
    },
    {
      "type": "BLOCKED",
      "module": "CreditorIndividualChecker",
      "message": "TBI Financial Services: REJECT ALL CASES. FCA complaint pending — do not run until response received.",
      "creditor": "TBI Financial Services"
    },
    {
      "type": "CONDITIONAL_VOTER_REQUIRED",
      "module": "ConditionalVoterHandler",
      "message": "Buddy Loans vote required to achieve majority. Minimum dividend 50p/£. Contact required before MOC.",
      "creditor": "Buddy Loans t/a Advancis Ltd"
    },
    {
      "type": "INFO",
      "module": "HMRCRulesChecker",
      "message": "HMRC debt below £4,000 — HMRC will not vote. This is neutral, not a block.",
      "creditor": "HM Revenue & Customs"
    }
  ],
  "creditor_positions": [
    {
      "creditor_name": "Moneybarn",
      "status": "REJECT",
      "reason": "Vehicle arrears 2+ months; arrangement call not confirmed",
      "representative": "DIRECT"
    }
  ],
  "council_positions": [],
  "majority_analysis": {
    "total_debt": 24000,
    "voting_debt": 15500,
    "majority_threshold": 7750,
    "majority_achievable": false,
    "conditional_voters_needed": ["Buddy Loans t/a Advancis Ltd"]
  },
  "dividend_analysis": {
    "estimated_pence": 28,
    "minimum_required_pence": 30,
    "shortfall_pence": 2,
    "creditors_below_minimum": ["Commsave Credit Union"]
  }
}

Build order

Database migrations — all tables and columns above
Seed county_council_routing (all 22+ counties with their districts)
Seed creditor_rules — priority order: TBI Financial Services, Moneybarn, Bamboo, Amigo, VW Financial Services, Buddy Loans, then all others
Seed representative_routing — all sub-brands for Barclaycard (14), Lloyds group, etc.
Seed debt_type_council_votes — Southwark, Lewisham, Durham, Portsmouth, Mid Suffolk
Seed conditional_voter_rules — Buddy Loans, Salary Finance
Seed creditor_open_banking_rules — Fintern/Abound, Everyday Loans, TM Advances, Bamboo
Build Phase 1 checkers — VehicleTerminationRisk and CountyCouncilRouter first
Build Phase 2 checkers — CreditorIndividual with all 22 columns, then Council
Build Phase 3–6 checkers in order
Build ResultAggregator — implement Colchester dividend conflict resolution rule (latest last_updated wins, council sheet takes precedence)
Integration tests per creditor listed in "critical individual creditor seed data"

The most urgent items before any coding starts: seed TBI Financial Services as REJECT/BLOCKED, add the is_currently_in_dmp field to the client payload, and implement VehicleTerminationRiskChecker — these three will cause incorrect live case approvals if absent.