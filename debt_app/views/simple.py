import dataclasses
import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from debt_app.criteria_engine import assess_case


@method_decorator(csrf_exempt, name='dispatch')
class AssessView(View):
    """POST /api/assess/ — internal-only, no auth."""

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

            # Add back ACCEPT creditors filtered out by engine
            engine_positions = result.get("creditor_positions", [])
            positioned_names = {
                p.get("creditor_name", "").strip().lower()
                for p in engine_positions
            } | {
                p.get("original_aryza_name", "").strip().lower()
                for p in engine_positions
                if p.get("original_aryza_name")
            }

            from debt_app.helpers import get_creditor_by_trading_name
            from debt_app.models import CreditorCriteria as _CC

            accept_positions = []
            for c in body.get("creditors") or []:
                cname = (c.get("creditor_name") or "").strip()
                original = (c.get("name") or cname).strip()
                if not cname:
                    continue
                if cname.lower() not in positioned_names and original.lower() not in positioned_names:
                    rep = "NONE"
                    try:
                        _crit = get_creditor_by_trading_name(cname)
                        rep = _crit.representative or "NONE"
                    except _CC.DoesNotExist:
                        pass
                    accept_positions.append({
                        "creditor_name": cname,
                        "original_aryza_name": original if original != cname else None,
                        "representative": rep,
                        "effective_status": "ACCEPT",
                        "balance": float(c.get("balance") or 0),
                    })
            
            result["creditor_positions"] = engine_positions + accept_positions
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
