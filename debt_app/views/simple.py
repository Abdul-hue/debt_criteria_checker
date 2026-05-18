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

        try:
            result = assess_case(body)
        except Exception as exc:
            return JsonResponse({'error': f'Engine error: {exc}'}, status=500)

        return JsonResponse({
            'overall': result['overall'],
            'representatives_detected': sorted(result['representatives_detected']),
            'hard_blocks': [dataclasses.asdict(r) for r in result['hard_blocks']],
            'flags':       [dataclasses.asdict(r) for r in result['flags']],
            'info':        [dataclasses.asdict(r) for r in result['info']],
            'passed':      [dataclasses.asdict(r) for r in result['passed']],
        })
