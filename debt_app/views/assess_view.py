import dataclasses
import json
import logging

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from debt_app.criteria_engine import assess_case, detect_representatives
from debt_app.recommendation_engine import get_recommendation

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class DirectAssessView(View):
    """
    POST /api/v1/assess/
    Plain Django view — no DRF, so csrf_exempt works reliably.
    """

    def post(self, request):
        # 1 — Parse body
        try:
            case_json = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Ensure name -> creditor_name mapping for engine (non-destructive)
        # Apply alias map for better representative detection
        from debt_app.helpers import CREDITOR_ALIAS_MAP
        for c in case_json.get("creditors") or []:
            raw_name = c.get("name") or c.get("creditor_name") or ""
            normalized = raw_name.strip().lower()
            resolved = CREDITOR_ALIAS_MAP.get(normalized, raw_name)
            
            c["creditor_name"] = resolved
            if "name" not in c:
                c["name"] = raw_name

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

            # STEP 7 — Add back ACCEPT creditors filtered out by engine
            engine_positions = result.get("creditor_positions", [])
            positioned_names = {
                p.get("creditor_name", "").strip().lower()
                for p in engine_positions
            }

            accept_positions = []
            for c in creditors:
                cname = (c.get("creditor_name") or "").strip()
                original = (c.get("name") or c.get("original_name") or cname).strip()
                if not cname:
                    continue
                if cname.lower() not in positioned_names:
                    accept_positions.append({
                        "creditor_name": cname,
                        "resolved_canonical_name": cname,
                        "original_aryza_name": original,
                        "effective_status": "ACCEPT",
                        "findings": [],
                        "reason": "Creditor accepted — no conditions apply",
                        "rule_ids": [],
                        "balance": float(c.get("balance") or 0),
                    })
            
            result["creditor_positions"] = engine_positions + accept_positions

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
                        "creditor_name":          c.get("creditor_name", ""),
                        "resolved_canonical_name": c.get("resolved_canonical_name", ""),
                        "representative":         c.get("representative", "NONE"),
                        "effective_status":        c.get("effective_status", "UNKNOWN"),
                        "balance":                 float(c.get("balance") or 0),
                        "reason":                  c.get("reason", ""),
                        "rule_ids":                c.get("rule_ids") or [],
                        "findings":                c.get("findings") or [],
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