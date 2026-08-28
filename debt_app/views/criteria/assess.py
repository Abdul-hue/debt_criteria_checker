"""Case assessment endpoints: POST /assess/ and the decision history views."""

import logging

from decimal import Decimal
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.integrations.aryza import fetch_case_by_reference
from debt_app.integrations.aryza import AryzaCaseNotFoundError
from debt_app.integrations.aryza import AryzaConnectionError
from debt_app.integrations.aryza import AryaTimeoutError
from debt_app.integrations.aryza import AryzaDataError
from debt_app.engine.criteria import assess_case
from debt_app.engine.criteria import detect_representatives
from debt_app.engine.criteria import _sanitize_dmp_checklist
from debt_app.engine.recommendation import get_recommendation
from debt_app.models import CreditorCriteria
from debt_app.models import CriteriaDecision
from debt_app.models import CouncilRule
from debt_app.models import Application
from debt_app.helpers import get_user_department
from debt_app.permissions import HasFeatureAccess
from debt_app.models import CreditReport
from debt_app.integrations.credit_report import normalise_start_date_iso

from debt_app.views.criteria._shared import (
    AssessRateThrottle,
    _rule_to_dict,
    _serialise_value,
    enrich_positions_with_tallies,
    enrich_rules_with_meta,
    error_response,
)

logger = logging.getLogger(__name__)

def build_phase7_response_fields(result: dict) -> dict:
    """Serialize assess_case result into a JSON-safe dict suitable for API responses."""
    def _rules(lst):
        return [_rule_to_dict(r) for r in lst]

    def _serialise_dict(d):
        if d is None:
            return None
        return {k: _serialise_value(v) for k, v in d.items()}

    return {
        "overall": result.get("overall"),
        "overall_status": result.get("overall_status"),
        "passes_all_hard_blocks": result.get("passes_all_hard_blocks"),
        "recommended_solution": result.get("recommended_solution"),
        "alternative_solutions": result.get("alternative_solutions", []),
        "tig_eligible": result.get("tig_eligible"),
        "hard_blocks": _rules(result.get("hard_blocks", [])),
        "flags": _rules(result.get("flags", [])),
        "info": _rules(result.get("info", [])),
        "passed": _rules(result.get("passed", [])),
        "creditor_positions": [
            {
                **pos,
                "balance": float(pos["balance"]) if isinstance(pos["balance"], Decimal) else pos["balance"],
            }
            for pos in result.get("creditor_positions", [])
        ],
        "council_positions": result.get("council_positions", []),
        "majority_analysis": _serialise_dict(result.get("majority_analysis")),
        "dividend_analysis": result.get("dividend_analysis"),
        "representatives_detected": list(result.get("representatives_detected") or []),
        "dmp_eligibility": result.get("dmp_eligibility"),
        "hmrc_is_creditor": result.get("hmrc_is_creditor", False),
    }


# DMP Eligibility Checklist fields. _evaluate_dmp_eligibility (engine/criteria.py)
# reads this full flat dict unchanged regardless of source — see build_dmp_checklist()
# below, which merges per-creditor-row dropdown selections with the remaining
# case-level checkboxes that have no reliable per-creditor signal.
DMP_CHECKLIST_FIELDS = [
    "current_year_council_tax",
    "previous_year_council_tax",
    "lost_right_to_pay_instalments",
    "current_gas_bill",
    "current_electric_bill",
    "previous_gas_provider_debt",
    "previous_electric_provider_debt",
    "current_water_bill",
    "council_parking_fine",
    "private_parking_debt",
    "current_phone_contract",
]


# Case-level checkboxes (Part 4 of the Aryza-only DMP redesign) — kept as a
# compact checklist since no reliable per-creditor signal exists for these:
# no gas/electric distinguishing signal in Aryza data, and
# lost_right_to_pay_instalments is a case-level fact, never per-row.
DMP_CASE_LEVEL_CHECKLIST_FIELDS = [
    "current_gas_bill",
    "current_electric_bill",
    "previous_gas_provider_debt",
    "previous_electric_provider_debt",
    "current_phone_contract",
    "lost_right_to_pay_instalments",
    # HMRC VAT (only offered when hmrc_is_creditor is true). hmrc_debt_has_vat is
    # the parent tick; hmrc_previous_year_vat is the only one that drives
    # behaviour — a confirmed previous-year VAT debt forces the case to DMP
    # (see _derive_recommended_solution). These flow through the flat checklist
    # dict but are read by _derive_recommended_solution, NOT by
    # _evaluate_dmp_eligibility (which only reads its own DMP_CHECKLIST_FIELDS).
    "hmrc_debt_has_vat",
    "hmrc_previous_year_vat",
]


def build_dmp_checklist(creditor_rows, case_level_raw):
    """
    Builds the flat DMP_CHECKLIST_FIELDS dict _evaluate_dmp_eligibility reads,
    combining (a) per-row dropdown selections from the Creditor Positions table
    and (b) the remaining DMP_CASE_LEVEL_CHECKLIST_FIELDS checkboxes.

    creditor_rows: list of {"debt_type_normalised": str, "value": str|None} —
      one entry per row where the caseworker made a dropdown selection.
      council_tax value: "current" | "previous"
      water value:       "current"
      pcn value:         "council" | "private"
      mobile value:      "current"
      A row left "Not set" (value None/absent) contributes nothing.
    case_level_raw: dict of the 6 DMP_CASE_LEVEL_CHECKLIST_FIELDS checkboxes.

    Multiple rows of the same type OR together (e.g. two council-tax rows,
    one "current" and one "previous", both set their respective flag True) —
    _evaluate_dmp_eligibility only reads case-wide booleans, not per-creditor
    identity, so this is the correct aggregation.
    """
    checklist = {field: False for field in DMP_CHECKLIST_FIELDS}
    for field in DMP_CASE_LEVEL_CHECKLIST_FIELDS:
        checklist[field] = bool((case_level_raw or {}).get(field, False))

    for row in creditor_rows or []:
        debt_type = row.get("debt_type_normalised") or row.get("type")
        value = row.get("value") or row.get("selection")
        if not value:
            continue
        if debt_type == "council_tax":
            if value == "current":
                checklist["current_year_council_tax"] = True
            elif value == "previous":
                checklist["previous_year_council_tax"] = True
        elif debt_type == "utility" and value == "current":
            # Water toggle is scoped to water-supplier names on the frontend
            # (DEBT_TYPE_UTILITY rows whose creditor_name matches a water
            # supplier) — see WATER_SUPPLIER_NAMES in the row-rendering logic.
            checklist["current_water_bill"] = True
        elif debt_type == "pcn":
            if value == "council":
                checklist["council_parking_fine"] = True
            elif value == "private":
                checklist["private_parking_debt"] = True
        elif debt_type == "mobile" and value == "current":
            checklist["current_phone_contract"] = True

    # Server-side guard: hmrc_previous_year_vat is only honoured when its parent
    # hmrc_debt_has_vat is also true. The frontend enforces this by only showing
    # the child tick once the parent is set, but a raw API call can submit the
    # child alone — and that tick is the highest-precedence forced-DMP override.
    # See _sanitize_dmp_checklist in engine/criteria.py.
    return _sanitize_dmp_checklist(checklist)


def build_uploaded_docs(aryza_reference: str) -> dict:
    """
    Returns empty document defaults.

    TODO: When Zubair's CA integration is complete,
    query EvidenceLedger by aryza_reference and map
    verified documents to this structure.
    """
    return {
        "wage_slips":                      [],
        "benefit_letter":                  False,
        "uc_journal":                      None,
        "tax_return":                      False,
        "business_bank_statement_months":  0,
        "cis_invoice":                     None,
        "proof_of_debt":                   {},
        "third_party_letter":              False,
        "termination_report":              False,
        "hmrc_submission_confirmed":       False,
        "car_finance_evidence":            False,
        "vehicle_hp_evidence":             False,
        "vulnerability_evidence":          False,
        "sustainability_paragraph":        False,
        "gamstop_proof":                   False,
        "clean_bank_statement_months":     0,
        "ie_changed_without_explanation":  False,
    }


class AssessCaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AssessRateThrottle]

    def _prepare_engine_payload(self, case_data_obj, credit_report_id=None):
        """
        Transforms Aryza CaseData object into the payload format expected by the criteria engine.

        Converts pence (int) to pounds (float).
        Excludes secured debt types (mortgage, hp, etc).
        Deduplicates on (creditor_name, debt_type, reference) — same name + type + reference = skip.
        Applies CREDITOR_ALIAS_MAP to resolve names BEFORE passing to engine.
        This ensures detect_representatives() matches correctly.

        credit_report_id: when given, pins credit-report enrichment to this EXACT
          CreditReport row (e.g. the id returned by upload-credit-report) instead of
          re-selecting among every historical extraction for this aryza_reference.

        Returns: (payload, prepared_creditors)
          payload: dict for assess_case()
          prepared_creditors: list of creditor dicts, used for ACCEPT creditor restoration
        """
        from rapidfuzz import fuzz, process as rfprocess
        from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name, normalise_debt_type, _SECURED_TYPES
        from debt_app.models import CountyCouncilRouting

        # Secured/unsecured classification uses the SAME normalise_debt_type()
        # helper the engine uses everywhere else (helpers.py) — this used to be
        # a hand-rolled exact-match set here that missed real Aryza values like
        # "Car HP" (space-separated, not the literal string "hp"), which let a
        # £17,007 secured car-finance debt get counted into the unsecured total.
        # One classifier, one place it can go wrong, instead of three.

        # Convert pence to pounds for all financial fields.
        # Never produce a negative DI — income=0 means fact find is incomplete,
        # not that the client owes money every month.
        _income_total_pence = (case_data_obj.income or {}).get("total", 0) or 0
        _expenditure_total_pence = (case_data_obj.expenditure or {}).get("total", 0) or 0
        if _income_total_pence > 0 and _expenditure_total_pence > 0:
            di_pounds = max(0, _income_total_pence - _expenditure_total_pence) / 100.0
        elif _income_total_pence > 0:
            di_pounds = 0.0  # income present but no SFS expenses yet
        else:
            # No income rows in client_income — fall back to Aryza's pre-computed DI
            # (td_client.td_contribution), already clamped to >= 0 by _calculate_totals.
            di_pounds = max(0, case_data_obj.disposable_income) / 100.0
        
        # Deduplication on (name, type, reference) — same entry only counted once
        seen_keys = set()
        prepared_creditors = []
        unsecured_debt_pounds = 0

        raw_creditors = case_data_obj.creditors or []

        # DB name lists — queried once before the loop, never per-creditor
        council_names = list(CouncilRule.objects.values_list('council_name', flat=True))
        county_names = list(CountyCouncilRouting.objects.values_list('county_name', flat=True))
        creditor_db_names = list(CreditorCriteria.objects.filter(is_active=True).values_list('creditor_name', flat=True))

        for creditor in raw_creditors:
            raw_name = (creditor.get('name') or '').strip()
            if not raw_name:
                continue

            debt_type = (creditor.get('type') or creditor.get('creditor_type') or '').strip().lower()
            ref = (creditor.get('ref') or creditor.get('reference') or '').strip().lower()

            # STEP 4 — secured/unsecured classification. The creditor is still
            # KEPT in prepared_creditors (so it shows up in the Creditor
            # Positions table, e.g. as "Does Not Vote") — it's just excluded
            # from unsecured_debt_pounds below. This mirrors how the
            # case-assessment tool sends secured debts: visible, tagged,
            # excluded from the unsecured total — rather than silently
            # disappearing from the creditor list.
            is_secured = normalise_debt_type(debt_type) in _SECURED_TYPES
            if is_secured:
                logger.warning(
                    f"[SECURED — excluded from unsecured total] '{raw_name}' type='{debt_type}'"
                )

            # --- 5-check name resolution waterfall ---
            resolved_name = raw_name
            debt_type_override = None

            # CHECK 1 — CouncilRule match (exact + '&'/'and' + suffix-strip).
            # NB: the old fuzz.partial_ratio>=85 matched on the shared
            # 'City Council' substring and mis-mapped e.g.
            # 'Brighton & Hove City Council' -> 'Derby City Council'. Use the same
            # robust resolver the engine uses at assessment so both agree.
            from debt_app.engine.criteria import _match_council_rule
            _council_rule = _match_council_rule(raw_name)
            if _council_rule is not None:
                logger.info(
                    "[COUNCIL MATCH] '%s' → '%s' — reclassified from type='%s' to council",
                    raw_name, _council_rule.council_name, debt_type,
                )
                resolved_name = _council_rule.council_name
                debt_type_override = 'council_tax'
            else:
                # CHECK 2 — CountyCouncilRouting fuzzy match (partial_ratio ≥ 85)
                _cr = rfprocess.extractOne(
                    raw_name, county_names, scorer=fuzz.partial_ratio, score_cutoff=85
                )
                if _cr:
                    _matched, _score, _ = _cr
                    logger.info(
                        "[COUNTY COUNCIL MATCH] '%s' → '%s' score=%d — "
                        "reclassified from type='%s' to council",
                        raw_name, _matched, _score, debt_type,
                    )
                    resolved_name = _matched
                    debt_type_override = 'council_tax'
                else:
                    # CHECK 3 — CreditorCriteria DB fuzzy match (token_sort_ratio ≥ 85)
                    _cr = rfprocess.extractOne(
                        raw_name, creditor_db_names, scorer=fuzz.token_sort_ratio, score_cutoff=85
                    )
                    if _cr:
                        _matched, _score, _ = _cr
                        logger.info(
                            "[CREDITOR DB MATCH] '%s' → '%s' score=%d — resolved from DB",
                            raw_name, _matched, _score,
                        )
                        resolved_name = _matched
                    else:
                        # CHECK 4 — CREDITOR_ALIAS_MAP exact match (existing behaviour)
                        # Keys in CREDITOR_ALIAS_MAP are normalised (legal suffixes stripped),
                        # so we must normalise the raw name before lookup.
                        _alias = CREDITOR_ALIAS_MAP.get(normalise_creditor_name(raw_name))
                        if _alias:
                            resolved_name = _alias
                        else:
                            # CHECK 5 — Aryza type fallback
                            logger.info(
                                "[CREDITOR UNRESOLVED] '%s' type='%s' — "
                                "no DB match, passing raw name",
                                raw_name, debt_type,
                            )

            balance_pence = creditor.get('balance') or creditor.get('total') or 0
            balance_pounds = float(balance_pence) / 100.0

            # STEP 5 — Deduplication on (name, type, reference, balance)
            # Including balance ensures that separate debts with the same name/type (e.g. 2 loans)
            # are not incorrectly merged when they lack a reference number.
            dedup_key = (raw_name.lower(), debt_type, ref, balance_pence)
            if dedup_key in seen_keys:
                logger.warning(
                    f"[TRUE DUPLICATE] '{raw_name}' type='{debt_type}' "
                    f"ref='{ref}' balance={balance_pounds} — skipping exact duplicate"
                )
                continue
            seen_keys.add(dedup_key)

            # Only count unsecured debts toward total
            if not is_secured:
                unsecured_debt_pounds += balance_pounds

            effective_type = debt_type_override if debt_type_override else debt_type
            creditor_dict = {
                **creditor,
                'creditor_name': resolved_name,
                'original_name': raw_name,
                'crm_balance': balance_pounds,
                'balance': balance_pounds,
                # Set both fields so _parse_case reads our intended type at priority 1
                # regardless of which field name Aryza used in the original payload.
                'creditor_type': effective_type,
                'debt_type_normalised': effective_type,
                'is_secured': is_secured,
            }
            prepared_creditors.append(creditor_dict)

            logger.warning(
                f"[PASS TO ENGINE] '{raw_name}' → '{resolved_name}' "
                f"balance=£{balance_pounds:,.2f} type='{effective_type}'"
            )

        # Enrich creditors with type_code and raw_name from credit report
        # Match by matched_creditor (lower) + balance (pence) for accuracy
        # Enrich creditors with CR data — match by name+balance (closest), carry all fields
        _cr_unmatched = []  # accounts in CR not matched to any declared creditor
        try:
            from debt_app.models import CreditReport
            cr_obj = None
            if credit_report_id:
                # Caller (e.g. the frontend, right after upload-credit-report)
                # knows exactly which extraction to use — pin to that row
                # instead of re-deriving "best" from history. Scoped to this
                # aryza_reference so a stray/mistyped id can't pull another
                # case's report.
                cr_obj = CreditReport.objects.filter(
                    id=credit_report_id,
                    aryza_reference=case_data_obj.aryza_reference,
                ).first()
                if not cr_obj:
                    logger.warning(
                        "[CR ENRICH] credit_report_id=%s not found for reference=%s — "
                        "falling back to most-recent extraction",
                        credit_report_id, case_data_obj.aryza_reference,
                    )
            if cr_obj is None:
                # No explicit id given (or it didn't resolve) — fall back to the
                # most recent extraction for this reference. Previously this
                # picked the extraction with the MOST accounts across ALL
                # history, which can silently resurrect a stale report: case
                # 349223 had four old extractions with 29 accounts each, then a
                # fresh, correct re-upload with only 26 — "most accounts wins"
                # kept serving the six-day-old 29-account report instead of the
                # one just uploaded. Recency is the right default; passing
                # credit_report_id explicitly is the reliable fix.
                recent_reports = CreditReport.objects.filter(
                    aryza_reference=case_data_obj.aryza_reference,
                    extraction_status="extracted",
                ).order_by('-created_at')
                cr_obj = next(
                    (r for r in recent_reports if (r.extracted_data or {}).get('accounts')),
                    None,
                )
            if cr_obj is None:
                # Nothing to enrich from — every creditor's CR columns (cr_balance,
                # cr_account_status, cr_missed_payments_3m, Match) will be left blank.
                # This is not an exception, so without an explicit log line it looks
                # to a caseworker like the feature was never implemented.
                logger.warning(
                    "[CR ENRICH] no extracted CreditReport found for reference=%s "
                    "(credit_report_id=%s) — creditor CR columns will be blank",
                    case_data_obj.aryza_reference, credit_report_id,
                )
            if cr_obj and cr_obj.extracted_data:
                # Mortgages are extracted into a SEPARATE list from unsecured/HP
                # accounts (mortgage_accounts vs accounts) — folding both in here
                # means a case's mortgage debt (e.g. "HBOS LLOYDS MORTGAGE") can
                # still be cross-checked against the credit report instead of
                # always showing no CR match.
                cr_accounts = (
                    (cr_obj.extracted_data.get('accounts', []) or []) +
                    (cr_obj.extracted_data.get('mortgage_accounts', []) or [])
                )

                # Build list of (normalised_name, balance_pence, full_account)
                # Include zero-balance accounts (bal=0 or None)
                cr_list = []
                for acc in cr_accounts:
                    mc = (acc.get('matched_creditor') or acc.get('raw_name') or '').lower().strip()
                    bal = acc.get('current_balance')  # pence, may be None
                    cr_list.append((mc, bal, acc))

                used_indices = set()

                # Tolerance on how far apart an Aryza balance and a credit-report
                # balance can be and still count as "the same account". A flat
                # £50 cap rejected genuine matches on larger balances that had
                # simply moved between the credit-report pull date and the
                # Aryza factfind date (e.g. a £9,760 debt vs an £8,791 CR
                # balance — £969 apart, clearly the same loan). Scaling with
                # the balance (20%, floor £50) keeps the original protection —
                # a shared/generic resolved name (e.g. two distinct Aryza debts
                # both aliased to "Monzo") still can't grab a wildly different
                # same-named CR account, since a wrong account is typically off
                # by far more than 20% — while tolerating normal balance drift.
                def _cr_match_tolerance_pence(aryza_bal_pence):
                    return max(5000, round(aryza_bal_pence * 0.20))

                for cd in prepared_creditors:
                    # Match on BOTH the resolved/representative name AND the
                    # raw Aryza name — a case creditor is often resolved to a
                    # representative-body brand (e.g. "Admiral Loans", "HBOS -
                    # Halifax - IVA", "Zopa - IVA or BKY") that shares no
                    # substring with the credit report's actual legal-entity
                    # name ("ADMIRAL FINANCIAL SERVICES LTD", "HALIFAX CREDIT
                    # CARD", "ZOPA LIMITED"). The raw Aryza name is much closer
                    # to the credit-bureau name, so trying both recovers these.
                    key_name = (cd.get('creditor_name') or '').lower().strip()
                    orig_name = (cd.get('original_name') or '').lower().strip()
                    # Aryza balance is in pounds — convert to pence for comparison
                    aryza_bal_pence = int(round((cd.get('balance') or 0) * 100))
                    tolerance_pence = _cr_match_tolerance_pence(aryza_bal_pence)

                    best_idx = None
                    best_diff = None

                    for i, (mc, bal, acc) in enumerate(cr_list):
                        if i in used_indices:
                            continue
                        name_match = (
                            mc == key_name or mc == orig_name or
                            (len(mc) >= 5 and (
                                mc in key_name or key_name in mc or
                                mc in orig_name or orig_name in mc
                            ))
                        )
                        if not name_match:
                            continue
                        # Balance match — treat None CR balance as 0
                        cr_bal = bal if bal is not None else 0
                        diff = abs(cr_bal - aryza_bal_pence)
                        # Only cap when the CR balance is actually known — if
                        # it's None there's nothing to compare, so fall back to
                        # the pre-existing name-only behaviour for that case.
                        if bal is not None and diff > tolerance_pence:
                            continue
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            best_idx = i

                    if best_idx is not None:
                        used_indices.add(best_idx)
                        acc = cr_list[best_idx][2]
                        cd['type_code']         = acc.get('type_code') or ''
                        cd['cr_raw_name']       = acc.get('raw_name') or ''
                        cd['cr_balance']        = acc.get('current_balance')  # pence
                        cd['cr_account_status']            = acc.get('account_status') or ''
                        cd['cr_account_status_subjective'] = acc.get('account_status_subjective') or ''
                        cd['cr_credit_limit']   = acc.get('credit_limit')
                        # ISO YYYY-MM-DD. Normalised on read as well as on
                        # extraction so credit reports stored before
                        # normalise_start_date_iso() existed (Experian
                        # DD-MM-YYYY, or no start_date at all) still render.
                        cd['cr_start_date']     = normalise_start_date_iso(acc.get('start_date'))
                        cd['cr_account_age_months'] = acc.get('account_age_months')
                        cd['cr_missed_payments_3m'] = acc.get('missed_payments_last_3_months')

                # Collect CR accounts that were NOT matched to any case creditor.
                # These will be backfilled into all_creditor_positions later so
                # caseworkers can see ALL accounts from the credit report regardless
                # of whether the client declared them in the case payload.
                _cr_unmatched = [
                    acc
                    for i, (_mc, _bal, acc) in enumerate(cr_list)
                    if i not in used_indices
                    and "application type" not in (acc.get('raw_name') or '').lower()
                ]

        except Exception as e:
            logger.warning(f"[CR ENRICH] failed: {e}")

        # Disambiguate duplicate creditor_name labels AFTER credit-report
        # matching (so the CR-enrich step above still matches against the
        # clean base name). Aryza's `creditor` table is one master record
        # per legal entity — a bank's current-account overdraft and its
        # separate credit card both join to the SAME creditorid, so
        # `creditor_name` is legitimately identical for two distinct debts
        # (confirmed: "Monzo Bank Limited" for both a Current Account and a
        # Credit Card debt in a live case). That's correct data, not a bug —
        # but showing two identically-labelled rows in the UI makes them
        # impossible to tell apart. Suffix the display name with its debt
        # type ONLY when it collides with another row in this same case.
        from collections import Counter
        _name_counts = Counter(cd.get('creditor_name') for cd in prepared_creditors)
        for cd in prepared_creditors:
            if _name_counts.get(cd.get('creditor_name'), 0) > 1:
                _type_label = (cd.get('debt_type_normalised') or cd.get('creditor_type') or '').replace('_', ' ').strip().title()
                if _type_label:
                    cd['creditor_name'] = f"{cd['creditor_name']} ({_type_label})"

        # Build the engine payload matching CASE_ASSESSMENT_PAYLOAD.md
        property_data = case_data_obj.property or {}
        vehicle_data = case_data_obj.vehicle or {}
        income_data = case_data_obj.income or {}
        expenditure_data = case_data_obj.expenditure or {}
        flags_data = case_data_obj.flags or {}
        payload = {
            "application_id": case_data_obj.aryza_reference,
            "client_name": case_data_obj.client_name,
            "clientInfo": {
                "dateOfBirth": case_data_obj.dob,
                "client_name": case_data_obj.client_name,
            },
            "employment_status": case_data_obj.employment_status,
            "disposable_income": di_pounds,
            "total_unsecured_debt": unsecured_debt_pounds,
            "financial_summary": {
                "net_balance": di_pounds,
                "total_income": (income_data.get("total") or 0) / 100.0,
                "income_source": case_data_obj.employment_status,
            },
            "crm_data": {
                "total_unsecured_debt": unsecured_debt_pounds,
            },
            "creditors": prepared_creditors,
            "income": {k: v/100.0 for k, v in income_data.items()},
            "expenditure": {k: v/100.0 for k, v in expenditure_data.items()},
            "third_party_contribution": (income_data.get("third_party_contribution", 0) or 0) / 100.0,
            "property": {
                "owns_property": property_data.get("owns_property", False),
                "property_value": (property_data.get("property_value") or 0) / 100.0 if property_data.get("property_value") is not None else 0.0,
                "mortgage_balance": (
                    (property_data.get("mortgage_balance") or 0) / 100.0
                    or sum(
                        float(cr.get("balance") or 0) / 100.0
                        for cr in (case_data_obj.creditors or [])
                        if (cr.get("type") or cr.get("creditor_type") or "").lower()
                        in {"mortgage", "secured", "secured_loan", "second_charge"}
                    )
                ),
                "equity": (property_data.get("equity") or 0) / 100.0 if property_data.get("equity") is not None else 0.0,
            },
            "vehicle": {
                "has_vehicle": vehicle_data.get("has_vehicle", False),
                "vehicle_value": (vehicle_data.get("vehicle_value") or 0) / 100.0 if vehicle_data.get("vehicle_value") else None,
                "hp_monthly_payment": (vehicle_data.get("hp_monthly_payment") or 0) / 100.0 if vehicle_data.get("hp_monthly_payment") else None,
            },
            "sfs_expenditure_breakdown": case_data_obj.sfs_expenditure_breakdown,
            "gold_transactions": case_data_obj.gold_transactions,
            "flags": flags_data,
            "previous_iva_failed_reason": flags_data.get("previous_iva_failed_reason"),
            "dependants": case_data_obj.dependants,
        }

        # Step 6 — Calculate aggregated benefit income for TIG-21.4
        # Rule TIG-21.4 requires the sum of all benefit components
        benefit_income_pence = (
            income_data.get("universal_credit", 0) or 0
        ) + (
            income_data.get("dla", 0) or 0
        ) + (
            income_data.get("pip", 0) or 0
        ) + (
            income_data.get("other_benefits", 0) or 0
        )

        benefit_income_pounds = benefit_income_pence / 100.0
        payload["benefit_income_amount"] = benefit_income_pounds if benefit_income_pounds > 0 else None
             
        return payload, prepared_creditors, _cr_unmatched


    def post(self, request):
        # Step 1 — Validate
        aryza_reference = (
            request.data.get("aryza_reference")
            or request.data.get("application_id")
        )
        if not aryza_reference:
            return error_response(
                "aryza_reference is required",
                "MISSING_REFERENCE",
                status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        credit_report_id = request.data.get("credit_report_id")
        # DMP Eligibility Checklist — combines per-row dropdown selections
        # (council tax current/previous, water included, parking
        # government/private, mobile) with the remaining case-level
        # checkboxes that have no reliable per-creditor signal (Part 4/5 of
        # the Aryza-only DMP redesign). See build_dmp_checklist().
        _creditor_rows = request.data.get("creditor_rows") or []
        _dmp_checklist_raw = request.data.get("dmp_checklist") or {}
        dmp_checklist = build_dmp_checklist(_creditor_rows, _dmp_checklist_raw)
        logger.warning(f"[DMP DEBUG] received creditor_rows={_creditor_rows!r} "
                       f"dmp_checklist_raw={_dmp_checklist_raw!r} -> built={dmp_checklist!r}")

        # Step 2 — Fetch from Aryza
        try:
            case_data_obj = fetch_case_by_reference(aryza_reference)
            case_data, prepared_creditors, _cr_unmatched = self._prepare_engine_payload(
                case_data_obj, credit_report_id,
            )
            # Phase A: attach as a new top-level payload key only — not read
            # by _parse_case or any rule function yet (see DMP_CHECKLIST_FIELDS).
            case_data["dmp_checklist"] = dmp_checklist
        except AryzaCaseNotFoundError:
            return error_response(
                f"Case {aryza_reference} not found in Aryza",
                "CASE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND
            )
        except AryaTimeoutError:
            return error_response(
                "Aryza database timed out. Please try again.",
                "ARYZA_TIMEOUT",
                status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AryzaConnectionError:
            return error_response(
                "Unable to connect to Aryza database.",
                "ARYZA_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AryzaDataError as e:
            logger.error("Aryza data error for %s: %s", aryza_reference, e)
            return error_response(
                "Data error reading case. Contact support.",
                "ARYZA_DATA_ERROR",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Step 3 — Run assessment engine
        # Fetch local evidence and flags to enrich the Aryza data
        try:
            from debt_app.models import Application, EvidenceLedger
            app_obj = Application.objects.filter(aryza_reference=aryza_reference).first()
            if app_obj:
                # First-assessment department tagging. Permanent snapshot of the
                # submitting user's department — set once, never overwritten by
                # later runs/users. This view allows anonymous access (AllowAny),
                # so we don't assume request.user is authenticated; if there's no
                # profile, get_user_department() falls back to "Default", which we
                # store as a real signal ("not Lead Gen") rather than leaving null.
                # We never create the Application row here — creation is admin-only
                # via ApplicationListView.post elsewhere.
                if not app_obj.source_department:
                    dept = get_user_department(request.user)
                    app_obj.source_department = dept.name if dept else None
                    app_obj.save(update_fields=['source_department'])

                # Feed into the engine payload so assess_case() can gate the
                # Lead Gen disposable-income formula / £399 auto-DRO rule on it.
                case_data["source_department"] = app_obj.source_department

                # Map EvidenceLedger to the format engine expects
                # Engine expects: [{"ref": "...", "is_verified": True, "category": "..."}]
                local_evidence = list(app_obj.evidence.all().values('entry_type', 'created_at'))
                # Since EvidenceLedger in models.py is minimal, we'll map entry_type to category
                # and assume created_at means it exists. We might need more fields in models.py later.
                case_data["evidence_ledger"] = [
                    {"category": e["entry_type"], "is_verified": True, "ref": e["entry_type"]} 
                    for e in local_evidence
                ]
                
                # Check for ClientFlags
                if hasattr(app_obj, 'client_flags'):
                    flags = app_obj.client_flags
                    case_data["is_currently_in_dmp"] = flags.is_currently_in_dmp
                    case_data["is_royal_mail_employee"] = flags.is_royal_mail_employee
                    case_data["is_police_officer"] = flags.is_police_officer
                    case_data["previous_iva_failed"] = flags.previous_iva_failed
        except Exception as e:
            logger.error(f"Failed to fetch local evidence/flags: {e}")

        # Normalise evidence_ledger — engine expects a list of 
        # {"category": str, "is_verified": bool, "ref": str} 
        # Guard against dict format from external callers 
        _ev = case_data.get("evidence_ledger", []) 
        if isinstance(_ev, dict): 
            case_data["evidence_ledger"] = [ 
                {"category": k, "is_verified": bool(v), "ref": k} 
                for k, v in _ev.items() 
            ] 
        elif not isinstance(_ev, list): 
            case_data["evidence_ledger"] = [] 

        case_creditors = case_data.get("creditors") or []
        detected_reps = detect_representatives(case_creditors)
        result = assess_case(case_data, detected_reps)

        # STEP 7 — Reconcile creditors the engine routed elsewhere (councils) or
        # could not assess. Uses the shared helper so the displayed status is always
        # the engine's CALCULATED value — councils reuse their real council_positions
        # status (e.g. Rother District Council = REJECT), and genuinely unidentified
        # creditors become UNKNOWN. NEVER a hardcoded ACCEPT.
        from debt_app.engine.criteria import reconcile_creditor_positions
        engine_positions = result.get("creditor_positions", [])
        all_creditor_positions = reconcile_creditor_positions(result, prepared_creditors)

        # STEP 7b — stamp CR fields onto engine position dicts, balance-aware dedup
        _pc_enriched = [
            pc for pc in prepared_creditors
            if pc.get('type_code') or pc.get('cr_raw_name')
        ]
        _used_pc = set()

        for pos in all_creditor_positions:
            pos_name = (pos.get('original_aryza_name') or pos.get('creditor_name') or '').lower().strip()
            pos_bal_pence = int(round((pos.get('balance') or 0) * 100))

            best_idx = None
            best_diff = None
            for i, pc in enumerate(_pc_enriched):
                if i in _used_pc:
                    continue
                pc_name = (pc.get('creditor_name') or '').lower().strip()
                pos_canonical = (pos.get('creditor_name') or '').lower().strip()
                name_match = (
                    pc_name == pos_name or
                    pc_name == pos_canonical or
                    (len(pc_name) >= 5 and (pc_name in pos_name or pos_name in pc_name)) or
                    (len(pc_name) >= 5 and (pc_name in pos_canonical or pos_canonical in pc_name))
                )
                if not name_match:
                    continue
                pc_bal_pence = int(round((pc.get('balance') or 0) * 100))
                diff = abs(pc_bal_pence - pos_bal_pence)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = i

            if best_idx is not None:
                _used_pc.add(best_idx)
                pc = _pc_enriched[best_idx]
                pos['type_code']             = pc.get('type_code') or ''
                pos['cr_raw_name']           = pc.get('cr_raw_name') or ''
                pos['cr_balance']            = pc.get('cr_balance')
                pos['cr_account_status']            = pc.get('cr_account_status') or ''
                pos['cr_account_status_subjective'] = pc.get('cr_account_status_subjective') or ''
                pos['cr_credit_limit']       = pc.get('cr_credit_limit')
                pos['cr_start_date']         = pc.get('cr_start_date')
                pos['cr_account_age_months'] = pc.get('cr_account_age_months')
                pos['cr_missed_payments_3m'] = pc.get('cr_missed_payments_3m')

        # Re-apply representative-body vote mapping over the combined list so any
        # backfilled (engine-missed) WATCH/TIX/EVOLVE creditor reflects its body's
        # outcome. Idempotent for engine positions already mapped in assess_case().
        from debt_app.engine.criteria import _apply_representative_outcomes
        _apply_representative_outcomes(
            all_creditor_positions,
            result.get("representative_outcomes") or {},
        )

        restored_count = len(all_creditor_positions) - len(engine_positions)
        logger.warning(
            f"[POSITIONS TOTAL] {len(engine_positions)} engine + "
            f"{restored_count} restored = "
            f"{len(all_creditor_positions)} total"
        )

        # STEP 7c — Backfill credit-report-only accounts.
        # Any CR account that was NOT matched to a case creditor is appended as
        # an informational "CREDITOR-CR-ONLY" row so caseworkers see the full
        # picture of the client's credit file, including undeclared accounts.
        if _cr_unmatched:
            # Build a set of cr_raw_names already stamped onto engine positions
            # (from Step 7b enrichment) so we never double-append.
            _already_stamped = {
                (pos.get('cr_raw_name') or '').lower().strip()
                for pos in all_creditor_positions
                if pos.get('cr_raw_name')
            }
            from debt_app.helpers import get_creditor_by_trading_name, normalise_creditor_name
            from debt_app.models import CreditorResolutionMiss

            for _acc in _cr_unmatched:
                _raw = ((_acc.get('raw_name') or '')).strip()
                if not _raw:
                    continue
                if _raw.lower() in _already_stamped:
                    continue
                _cr_bal_pence = _acc.get('current_balance')
                _cr_name = _acc.get('matched_creditor') or _raw

                # Resolve against the SAME CreditorCriteria table/alias map used
                # for declared creditors — a CR-only (undeclared) account is not
                # exempt from representative-body voting just because it never
                # reached _check_creditor_individual(). Previously this branch
                # hardcoded representative='NONE' unconditionally, which meant a
                # genuinely WATCH/TIX/EVOLVE creditor that only showed up as an
                # undeclared credit-report account silently lost its badge.
                try:
                    _cr_criteria = get_creditor_by_trading_name(_cr_name)
                    _cr_representative = _cr_criteria.representative
                except CreditorCriteria.DoesNotExist:
                    _cr_representative = 'NONE'
                    try:
                        CreditorResolutionMiss.objects.create(
                            raw_name=_raw,
                            normalised_name=normalise_creditor_name(_raw) or _raw,
                            case_reference=aryza_reference,
                            client_name=case_data.get('client_name', ''),
                            balance=(_cr_bal_pence or 0) / 100.0,
                        )
                    except Exception as e:
                        logger.error(f"Failed to log CreditorResolutionMiss for CR-only account {_raw!r}: {e}")

                _cr_only_pos = {
                    'criteria_id': None,
                    'creditor_name': _cr_name,
                    'display_name': None,
                    'original_aryza_name': _raw if _raw != _cr_name else None,
                    'resolved_canonical_name': _cr_name,
                    'representative': _cr_representative,
                    'effective_status': 'UNKNOWN',
                    'findings': [{
                        'code': 'CREDITOR-CR-ONLY',
                        'reason': (
                            'This account appears on the customer\'s credit report but '
                            'was not declared as a debt on this case. The caseworker '
                            'should confirm with the customer whether this debt exists '
                            'and should be added.'
                        ),
                        'severity': 'info',
                    }],
                    'reason': (
                        'This account appears on the customer\'s credit report but '
                        'was not declared as a debt on this case. The caseworker '
                        'should confirm with the customer whether this debt exists '
                        'and should be added.'
                    ),
                    'rule_ids': ['CREDITOR-CR-ONLY'],
                    'balance': 0.0,  # £0 — not declared in case
                    'criteria_notes': '',
                    'dividend_notes': '',
                    'is_secured': False,
                    'debt_type_normalised': None,
                    '_creditor_idx': None,
                    'cr_raw_name': _raw,
                    'type_code': _acc.get('type_code') or '',
                    'cr_balance': _cr_bal_pence,
                    'cr_account_status': _acc.get('account_status') or '',
                    'cr_account_status_subjective': _acc.get('account_status_subjective') or '',
                    'cr_credit_limit': _acc.get('credit_limit'),
                    'cr_start_date': normalise_start_date_iso(_acc.get('start_date')),
                    'cr_account_age_months': _acc.get('account_age_months'),
                    'cr_missed_payments_3m': _acc.get('missed_payments_last_3_months'),
                }
                all_creditor_positions.append(_cr_only_pos)
                logger.info(
                    f"[CR-ONLY] Backfilled undeclared account: {_raw!r} "
                    f"(CR balance: {_cr_bal_pence}p, status: {_acc.get('account_status')!r})"
                )

            # Re-apply the representative-body outcome mapping now that CR-only
            # accounts have been appended. The first call (above, before this
            # block) ran before these positions existed, so a CR-only account
            # correctly resolved to e.g. TIX would otherwise show the TIX badge
            # but stay stuck at effective_status='UNKNOWN' — the outcome was
            # never applied because the position didn't exist yet when that
            # call ran. Documented as idempotent, so re-running it over
            # everything (not just the new positions) is safe.
            _apply_representative_outcomes(
                all_creditor_positions,
                result.get("representative_outcomes") or {},
            )

        enrich_positions_with_tallies(all_creditor_positions)
        result["creditor_positions"] = all_creditor_positions
        
        # Enrich rules with metadata from GlobalCriteria
        result['hard_blocks'] = enrich_rules_with_meta(result.get('hard_blocks', []))
        result['flags'] = enrich_rules_with_meta(result.get('flags', []))
        result['passed'] = enrich_rules_with_meta(result.get('passed', []))
        result['info'] = enrich_rules_with_meta(result.get('info', []))

        # Determine decision and get recommendation
        hard_blocks = result.get("hard_blocks", [])
        flags = result.get("flags", [])
        
        if hard_blocks:
            decision = "INELIGIBLE"
        elif flags:
            decision = "REFERRED"
        else:
            decision = "ELIGIBLE"
            
        # Captured BEFORE the overwrite two lines down — assess_case's own
        # _derive_recommended_solution already computed "FORCED_DMP_VAT" as the
        # single source of truth for the VAT-override precedence; get_recommendation
        # must honour it rather than silently recompute a different decision from
        # hard_blocks/flags alone (that was the bug: this view used to discard it).
        vat_forced = result.get("recommended_solution") == "FORCED_DMP_VAT"
        # Same capture pattern as vat_forced, for the Lead Gen £399 auto-DRO rule.
        # Mutually exclusive with vat_forced by construction — assess_case routes
        # a case where both conditions fire to "REVIEW_REQUIRED" instead, so at
        # most one of vat_forced/dro_forced is ever True here.
        dro_forced = result.get("recommended_solution") == "FORCED_DRO_LG"
        recommendations = get_recommendation(
            decision, result, case_data, vat_forced=vat_forced, dro_forced=dro_forced,
        )
        result["recommended_solution"] = recommendations.get("recommended_solution")
        result["alternative_solutions"] = recommendations.get("alternative_solutions", [])

        serialized = build_phase7_response_fields(result)

        # Attach financial summary fields that are NOT produced by build_phase7_response_fields
        # but are required for correct display when the saved result is later reloaded.
        # Without this, reloading from history always shows disposable_income = 0.
        serialized["disposable_income"] = case_data.get("disposable_income")
        serialized["total_unsecured_debt"] = case_data.get("total_unsecured_debt")
        serialized["lead_gen_disposable_income"] = result.get("lead_gen_disposable_income")

        # Step 4 — Save to CriteriaDecision
        try:
            # Clear previous history for this reference to satisfy "no history" requirement
            CriteriaDecision.objects.filter(application_id=aryza_reference).delete()

            # recommended_solution field in DB expects a string (the code)
            db_recommended_solution = result["recommended_solution"].get("code", "UNCLEAR") if isinstance(result["recommended_solution"], dict) else (result["recommended_solution"] or "UNCLEAR")

            decision_obj = CriteriaDecision.objects.create(
                application_id=aryza_reference,
                client_name=case_data.get("client_name", "Unknown"),
                input_snapshot=case_data,
                decision_output=serialized,
                recommended_solution=db_recommended_solution,
                passes_all_hard_blocks=serialized.get("passes_all_hard_blocks", False),
                triggered_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
                source="STANDALONE"
            )
            decision_id = str(decision_obj.id)
        except Exception as e:
            logger.error("Failed to save CriteriaDecision: %s", e)
            decision_id = None

        logger.info("Assessment completed for %s: %s", aryza_reference, serialized.get("recommended_solution"))
        return Response({
            "success": True,
            "decision_id": decision_id,
            "client_name": case_data_obj.client_name,
            "aryza_reference": aryza_reference,
            "evaluated_at": timezone.now().isoformat(),
            "disposable_income": case_data.get("disposable_income"),
            "total_unsecured_debt": case_data.get("total_unsecured_debt"),
            **serialized,
        }, status=status.HTTP_200_OK)


class AssessHistoryView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasFeatureAccess]
    required_feature = 'decisions'

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        reference = request.query_params.get('reference', '')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = CriteriaDecision.objects.all().order_by('-triggered_at')

        if reference:
            queryset = queryset.filter(application_id__icontains=reference)

        if date_from:
            parsed_date = parse_date(date_from)
            if parsed_date:
                queryset = queryset.filter(triggered_at__date__gte=parsed_date)

        if date_to:
            parsed_date = parse_date(date_to)
            if parsed_date:
                queryset = queryset.filter(triggered_at__date__lte=parsed_date)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        results = []
        for decision in page_obj:
            results.append({
                "id": str(decision.id),
                "aryza_reference": decision.application_id,
                "client_name": decision.client_name,
                "recommended_solution": decision.recommended_solution,
                "passes_all_hard_blocks": decision.passes_all_hard_blocks,
                "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
                "created_at": decision.triggered_at.isoformat(),
                "result_json": decision.result_json,
                "decision_output": decision.decision_output,
            })

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": results,
        }, status=status.HTTP_200_OK)


class AssessHistoryDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, id):
        try:
            return CriteriaDecision.objects.get(id=id)
        except CriteriaDecision.DoesNotExist:
            return None

    def get(self, request, id):
        decision = self._get_object(id)
        if decision is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "id": str(decision.id),
            "application_id": decision.application_id,
            "client_name": decision.client_name,
            "input_snapshot": decision.input_snapshot,
            "decision_output": decision.decision_output,
            "result_json": decision.result_json,
            "recommended_solution": decision.recommended_solution,
            "passes_all_hard_blocks": decision.passes_all_hard_blocks,
            "triggered_by": decision.triggered_by.username if decision.triggered_by else None,
            "triggered_at": decision.triggered_at.isoformat(),
            "source": decision.source,
        }, status=status.HTTP_200_OK)

    def delete(self, request, id):
        decision = self._get_object(id)
        if decision is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        decision.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
