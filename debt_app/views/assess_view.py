import dataclasses
import json
import logging

from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from debt_app.criteria_engine import assess_case, detect_representatives
from debt_app.recommendation_engine import get_recommendation

logger = logging.getLogger(__name__)


def _council_default_reason(name: str, status: str) -> str:
    if status == "ACCEPT":
        return f"{name} — council tax debt accepted into the IVA under standard terms"
    if status == "REJECT":
        return f"{name} — council creditor rejects inclusion in this IVA proposal"
    if status == "DO_NOT_VOTE":
        return f"{name} — council creditor does not participate in the creditor vote"
    return f"{name} — council creditor status calculated by council rules engine"


class DirectAssessView(APIView):
    """
    POST /api/v1/assess/
    Open endpoint — no JWT required. The CA backend and any authorised
    service-to-service caller can POST raw case JSON without a token.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # 1 — Parse body
        try:
            case_json = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Ensure name -> creditor_name mapping for engine (non-destructive)
        # Apply alias map for better representative detection.
        # CREDITOR_ALIAS_MAP keys are pre-normalised via normalise_creditor_name()
        # (legal suffixes stripped), so we must normalise before lookup or names
        # like "MBNA Limited" would miss the "mbna" key and go unresolved.
        from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name
        for c in case_json.get("creditors") or []:
            raw_name = c.get("name") or c.get("creditor_name") or ""
            normalized = normalise_creditor_name(raw_name)
            resolved = CREDITOR_ALIAS_MAP.get(normalized, raw_name)
            
            c["creditor_name"] = resolved
            if "name" not in c:
                c["name"] = raw_name

        # Enrich creditors with credit report data
        try:
            from debt_app.models import CreditReport
            aryza_reference = case_json.get("application_id") or case_json.get("aryza_reference")
            if aryza_reference:
                recent_reports = CreditReport.objects.filter(
                    aryza_reference=aryza_reference,
                    extraction_status="extracted",
                ).order_by("-created_at")
                cr_obj = next(
                    (r for r in recent_reports if (r.extracted_data or {}).get('accounts')),
                    None,
                )
                if cr_obj and cr_obj.extracted_data:
                    # Merge accounts and mortgage accounts
                    cr_accounts = (
                        (cr_obj.extracted_data.get('accounts', []) or []) +
                        (cr_obj.extracted_data.get('mortgage_accounts', []) or [])
                    )

                    # Build list of (normalised_name, balance_pence, full_account)
                    cr_list = []
                    for acc in cr_accounts:
                        mc = (acc.get('matched_creditor') or acc.get('raw_name') or '').lower().strip()
                        bal = acc.get('current_balance')  # pence, may be None
                        cr_list.append((mc, bal, acc))

                    used_indices = set()

                    def _cr_match_tolerance_pence(aryza_bal_pence):
                        return max(5000, round(aryza_bal_pence * 0.20))

                    for c in case_json.get("creditors") or []:
                        key_name = (c.get("creditor_name") or '').lower().strip()
                        orig_name = (c.get("name") or c.get("original_name") or '').lower().strip()
                        # Aryza balance is in pounds — convert to pence for comparison
                        aryza_bal_pence = int(round((float(c.get("balance") or 0) or 0) * 100))
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
                            if bal is not None and diff > tolerance_pence:
                                continue
                            if best_diff is None or diff < best_diff:
                                best_diff = diff
                                best_idx = i

                        if best_idx is not None:
                            used_indices.add(best_idx)
                            acc = cr_list[best_idx][2]
                            c['type_code'] = acc.get('type_code') or ''
                            c['cr_raw_name'] = acc.get('raw_name') or ''
                            c['cr_balance'] = acc.get('current_balance')  # pence
                            c['cr_account_status'] = acc.get('account_status') or ''
                            c['cr_account_status_subjective'] = acc.get('account_status_subjective') or ''
                            c['cr_credit_limit'] = acc.get('credit_limit')
                            c['cr_account_age_months'] = acc.get('account_age_months')
                            c['cr_missed_payments_3m'] = acc.get('missed_payments_last_3_months')

        except Exception as e:
            logger.warning(f"[CR Enrichment failed in DirectAssessView] {e}")

        # 2 — Detect representatives and run engine
        try:
            # Normalise evidence_ledger — engine expects a list of
            # {"category": str, "is_verified": bool, "ref": str}
            # Guard against dict format from external callers (CA Tool fallback)
            _ev = case_json.get("evidence_ledger", [])
            if isinstance(_ev, dict):
                case_json["evidence_ledger"] = [
                    {"category": k, "is_verified": bool(v), "ref": k}
                    for k, v in _ev.items()
                ]
            elif not isinstance(_ev, list):
                case_json["evidence_ledger"] = []

            creditors = case_json.get("creditors") or []
            detected_reps = detect_representatives(creditors)
            result = assess_case(case_json, detected_reps)

            # STEP 7 — Surface any creditors the engine did not position, using the
            # shared reconciliation helper so status is always the engine's CALCULATED
            # value: councils reuse their real council_positions status; anything
            # genuinely unrecognised is UNKNOWN. Never a hardcoded ACCEPT.
            from debt_app.criteria_engine import reconcile_creditor_positions
            engine_positions = result.get("creditor_positions", [])
            result["creditor_positions"] = reconcile_creditor_positions(result, creditors)

            # STEP 7b — stamp CR fields onto engine position dicts, balance-aware dedup
            _pc_enriched = [
                pc for pc in creditors
                if pc.get('type_code') or pc.get('cr_raw_name')
            ]
            _used_pc = set()

            for pos in result["creditor_positions"]:
                pos_name = (pos.get('original_aryza_name') or pos.get('creditor_name') or '').lower().strip()
                pos_bal_pence = int(round((pos.get('balance') or 0) * 100))

                best_idx = None
                best_diff = None
                for i, pc in enumerate(_pc_enriched):
                    if i in _used_pc:
                        continue
                    pc_name = (pc.get('creditor_name') or pc.get('name') or '').lower().strip()
                    pos_canonical = (pos.get('creditor_name') or '').lower().strip()
                    name_match = (
                        pc_name == pos_name or
                        pc_name == pos_canonical or
                        (len(pc_name) >= 5 and (pc_name in pos_name or pos_name in pc_name)) or
                        (len(pc_name) >= 5 and (pc_name in pos_canonical or pos_canonical in pc_name))
                    )
                    if not name_match:
                        continue
                    pc_bal_pence = int(round((pc.get('balance') or pc.get('crm_balance') or 0) * 100))
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
                    pos['cr_account_age_months'] = pc.get('cr_account_age_months')
                    pos['cr_missed_payments_3m'] = pc.get('cr_missed_payments_3m')

            # Re-apply representative-body vote mapping over the combined list so
            # any backfilled (engine-missed) creditor that resolves to a WATCH/TIX/
            # EVOLVE body also reflects its body's outcome. Idempotent for the
            # engine positions already mapped inside assess_case().
            from debt_app.criteria_engine import _apply_representative_outcomes
            _apply_representative_outcomes(
                result["creditor_positions"],
                result.get("representative_outcomes") or {},
            )

            from debt_app.views.criteria_views import enrich_positions_with_tallies
            enrich_positions_with_tallies(result["creditor_positions"])

            # Determine decision and get recommendation
            hard_blocks = result.get("hard_blocks", [])
            flags = result.get("flags", [])
            
            if hard_blocks:
                decision = "INELIGIBLE"
            elif flags:
                decision = "REFERRED"
            else:
                decision = "ELIGIBLE"
                
            recommendations = get_recommendation(decision, result, case_json)
            result["recommended_solution"] = recommendations.get("recommended_solution")
            result["alternative_solutions"] = recommendations.get("alternative_solutions", [])

        except Exception as exc:
            logger.exception("Engine error during /api/v1/assess/")
            return JsonResponse(
                {"error": "Engine error", "detail": str(exc)},
                status=500,
            )

        # 3 — Serialise response
        try:
            maj = result.get("majority_analysis") or {}
            div = result.get("dividend_analysis") or {}

            response_body = {
                # ── top-level status ──────────────────────────────────────
                "overall":                result["overall"],
                "overall_status":         result.get("overall_status", result["overall"].upper()),
                "passes_all_hard_blocks": result.get("passes_all_hard_blocks", False),
                "tig_eligible":           result.get("tig_eligible", False),
                "recommended_solution":   result.get("recommended_solution"),
                "alternative_solutions":   result.get("alternative_solutions", []),
                "representatives_detected": sorted(result.get("representatives_detected") or []),

                # ── summary counts ────────────────────────────────────────
                "summary": {
                    "hard_block_count": len(result.get("hard_blocks") or []),
                    "flag_count":       len(result.get("flags") or []),
                    "info_count":       len(result.get("info") or []),
                    "passed_count":     len(result.get("passed") or []),
                },

                # ── rule results ──────────────────────────────────────────
                "hard_blocks": [dataclasses.asdict(r) for r in (result.get("hard_blocks") or [])],
                "flags":       [dataclasses.asdict(r) for r in (result.get("flags") or [])],
                "info":        [dataclasses.asdict(r) for r in (result.get("info") or [])],
                "passed":      [dataclasses.asdict(r) for r in (result.get("passed") or [])],

                # ── creditor positions ────────────────────────────────────
                "creditor_positions": [
                    {
                        "criteria_id":            c.get("criteria_id"),
                        "creditor_name":          c.get("creditor_name", ""),
                        "display_name":           c.get("display_name"),
                        "original_aryza_name":    c.get("original_aryza_name"),
                        "resolved_canonical_name": c.get("resolved_canonical_name", ""),
                        "representative":         c.get("representative", "NONE"),
                        # Rep-body booleans derived from `representative` so
                        # consumers (CA Tool verification table) can label the
                        # row without re-deriving against a local copy. Covers
                        # engine positions and the ACCEPT backfill uniformly.
                        "is_watch":               (c.get("representative") or "").upper() == "WATCH",
                        "is_tix":                 (c.get("representative") or "").upper() == "TIX",
                        "is_evolve":              (c.get("representative") or "").upper() == "EVOLVE",
                        "effective_status":        c.get("effective_status", "UNKNOWN"),
                        "balance":                 float(c.get("balance") or 0),
                        "reason":                  c.get("reason", ""),
                        "rule_ids":                c.get("rule_ids") or [],
                        "findings":                c.get("findings") or [],
                        "type_code":               c.get("type_code") or "",
                        "cr_raw_name":             c.get("cr_raw_name") or "",
                        "cr_balance":              c.get("cr_balance"),
                        "cr_account_status":            c.get("cr_account_status") or "",
                        "cr_account_status_subjective": c.get("cr_account_status_subjective") or "",
                        "cr_credit_limit":         c.get("cr_credit_limit"),
                        "cr_account_age_months":   c.get("cr_account_age_months"),
                        "cr_missed_payments_3m":   c.get("cr_missed_payments_3m"),
                        "outcomes_approved":      c.get("outcomes_approved", 0),
                        "outcomes_disapproved":   c.get("outcomes_disapproved", 0),
                        "outcomes_total":         c.get("outcomes_total", 0),
                        # CRM aggregate vote history from CreditorVoteSummary
                        "crm_total_votes":        c.get("crm_total_votes", 0),
                        "crm_accepted_count":     c.get("crm_accepted_count", 0),
                        "crm_rejected_count":     c.get("crm_rejected_count", 0),
                        "crm_modified_count":     c.get("crm_modified_count", 0),
                        "crm_pod_count":          c.get("crm_pod_count", 0),
                    }
                    for c in (result.get("creditor_positions") or [])
                ],

                # ── council positions ─────────────────────────────────────
                "council_positions": [
                    {
                        "council_name":    c.get("council_name", ""),
                        "creditor_name":   c.get("creditor_name", ""),
                        "effective_status": c.get("effective_status", "UNKNOWN"),
                        "findings":        c.get("findings") or [],
                    }
                    for c in (result.get("council_positions") or [])
                ],

                # ── majority analysis ─────────────────────────────────────
                "majority_analysis": {
                    "total_debt":  float(maj.get("total_debt") or 0),
                    "threshold":   float(maj.get("threshold") or 0),
                    "voting_debt": float(maj.get("voting_debt") or 0),
                    "shortfall":   float(maj.get("shortfall") or 0),
                    "achievable":  bool(maj.get("achievable", False)),
                },

                # ── dividend analysis ─────────────────────────────────────
                "dividend_analysis": {
                    "estimated_pence":    int(div.get("estimated_pence") or 0),
                    "min_required_pence": int(div.get("min_required_pence") or 0),
                    "below_min": [
                        {
                            "creditor_name":      b.get("creditor_name", ""),
                            "balance":            float(b.get("balance") or 0),
                            "min_dividend_pence": int(b.get("min_dividend_pence") or 0),
                            "estimated_pence":    int(b.get("estimated_pence") or 0),
                            "shortfall_pence":    int(b.get("shortfall_pence") or 0),
                            "code":               b.get("code", ""),
                        }
                        for b in (div.get("below_min") or [])
                    ],
                },
            }
        except Exception as exc:
            logger.exception("Serialisation error in /api/v1/assess/")
            return JsonResponse(
                {"error": "Internal server error", "detail": str(exc)},
                status=500,
            )

        return JsonResponse(response_body)