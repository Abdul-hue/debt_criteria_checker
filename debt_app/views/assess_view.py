import dataclasses
import json
import logging

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from debt_app.criteria_engine import assess_case, detect_representatives

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

        # 2 — Detect representatives and run engine
        try:
            creditors = case_json.get("creditors") or []
            detected_reps = detect_representatives(creditors)
            result = assess_case(case_json, detected_reps)
        except Exception as exc:
            logger.exception("Engine error during /api/v1/assess/")
            return JsonResponse(
                {"error": "Engine error", "detail": str(exc)},
                status=500,
            )

        # 3 — Serialise response
        try:
            response_body = {
                "overall": result["overall"],
                "representatives_detected": sorted(result["representatives_detected"]),
                "summary": {
                    "hard_block_count": len(result["hard_blocks"]),
                    "flag_count":       len(result["flags"]),
                    "info_count":       len(result["info"]),
                    "passed_count":     len(result["passed"]),
                },
                "hard_blocks": [dataclasses.asdict(r) for r in result["hard_blocks"]],
                "flags":       [dataclasses.asdict(r) for r in result["flags"]],
                "info":        [dataclasses.asdict(r) for r in result["info"]],
                "passed":      [dataclasses.asdict(r) for r in result["passed"]],
            }
        except Exception as exc:
            logger.exception("Serialisation error in /api/v1/assess/")
            return JsonResponse(
                {"error": "Internal server error", "detail": str(exc)},
                status=500,
            )

        return JsonResponse(response_body)