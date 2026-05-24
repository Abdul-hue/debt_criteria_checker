import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.models import CriteriaDecision

logger = logging.getLogger(__name__)

class EvaluationHistoryView(APIView):
    """
    GET /api/v1/cases/<case_id>/evaluations
    Returns a paginated list of evaluation history for a specific case.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id):
        # 1. Query CriteriaDecision for all records matching application_id (case_id)
        # Ordered by triggered_at descending (most recent first)
        queryset = CriteriaDecision.objects.filter(
            application_id=case_id
        ).select_related('triggered_by').order_by('-triggered_at')

        # 2. Pagination
        page_size = 10
        page_number = request.query_params.get('page', 1)
        paginator = Paginator(queryset, page_size)

        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            return Response({
                "results": [],
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "current_page": int(page_number)
            }, status=status.HTTP_200_OK)

        # 3. Map results to the required lightweight shape
        results = []
        for decision in page_obj:
            # Safely extract from result_json if available, otherwise fallback to model fields
            res_json = decision.result_json or {}
            
            # Extract username or full name
            evaluated_by = "System"
            if decision.triggered_by:
                evaluated_by = decision.triggered_by.get_full_name() or decision.triggered_by.username

            results.append({
                "evaluation_id": str(decision.id),
                "decision": res_json.get("decision", decision.recommended_solution),
                "evaluated_at": decision.triggered_at.isoformat(),
                "evaluated_by": evaluated_by,
                "recommended_solution": res_json.get("recommended_solution", {
                    "code": decision.recommended_solution,
                    "label": decision.get_recommended_solution_display(),
                    "confidence": "UNKNOWN"
                }),
                "requires_review": res_json.get("requires_review", not decision.passes_all_hard_blocks),
                "flagged_criteria_count": len(res_json.get("flagged_criteria", []))
            })

        return Response({
            "results": results,
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous()
        }, status=status.HTTP_200_OK)
