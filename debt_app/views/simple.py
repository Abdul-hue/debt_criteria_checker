import dataclasses
import json

from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.criteria_engine import assess_case
from debt_app.permissions import HasFeatureAccess


class AssessView(APIView):
    """POST /api/assess/"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasFeatureAccess]
    required_feature = 'run_assessment'

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Request body must be valid JSON'},
                status=400,
            )

        if not isinstance(body, dict):
            return JsonResponse(
                {'error': 'Request body must be a JSON object, not a list or scalar'},
                status=400,
            )

        # Ensure name -> creditor_name mapping for engine (non-destructive)
        # Apply alias map for better representative detection.
        # CREDITOR_ALIAS_MAP keys are pre-normalised via normalise_creditor_name()
        # (legal suffixes stripped), so we must normalise before lookup or names
        # like "MBNA Limited" would miss the "mbna" key and go unresolved.
        from debt_app.helpers import CREDITOR_ALIAS_MAP, normalise_creditor_name
        for c in body.get("creditors") or []:
            raw_name = c.get("name") or c.get("creditor_name") or ""
            normalized = normalise_creditor_name(raw_name)
            resolved = CREDITOR_ALIAS_MAP.get(normalized, raw_name)
            
            c["creditor_name"] = resolved
            if "name" not in c:
                c["name"] = raw_name

        try:
            # Normalise evidence_ledger — engine expects a list of
            # {"category": str, "is_verified": bool, "ref": str}
            # Guard against dict format from external callers (CA Tool fallback)
            _ev = body.get("evidence_ledger", [])
            if isinstance(_ev, dict):
                body["evidence_ledger"] = [
                    {"category": k, "is_verified": bool(v), "ref": k}
                    for k, v in _ev.items()
                ]
            elif not isinstance(_ev, list):
                body["evidence_ledger"] = []

            result = assess_case(body)

            # Reconcile creditors the engine routed elsewhere (councils) or could not
            # assess, using the shared helper so status is always the engine's
            # CALCULATED value — never a hardcoded ACCEPT.
            from debt_app.criteria_engine import reconcile_creditor_positions
            result["creditor_positions"] = reconcile_creditor_positions(
                result, body.get("creditors") or []
            )
        except Exception as exc:
            return JsonResponse({'error': f'Engine error: {exc}'}, status=500)

        return JsonResponse({
            'overall': result['overall'],
            'representatives_detected': sorted(result['representatives_detected']),
            'hard_blocks': [dataclasses.asdict(r) for r in result['hard_blocks']],
            'flags':       [dataclasses.asdict(r) for r in result['flags']],
            'info':        [dataclasses.asdict(r) for r in result['info']],
            'passed':      [dataclasses.asdict(r) for r in result['passed']],
            'creditor_positions': result.get('creditor_positions', []),
        })
