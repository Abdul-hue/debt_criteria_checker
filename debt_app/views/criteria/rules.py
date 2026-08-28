"""Global criteria rule CRUD and rule change history."""

from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import GlobalCriteria
from debt_app.models import CriteriaDecision
from debt_app.helpers import filter_by_department
from debt_app.permissions import HasWritePermission
from debt_app.permissions import HasReadPermission
from debt_app.models import DepartmentRuleVisibility

def _rule_obj_to_dict(rule, include_full=False):
    """
    Convert a GlobalCriteria object to a dictionary.
    
    Args:
        rule: GlobalCriteria instance
        include_full: If True, include all documentation and reference fields
    """
    basic = {
        "id": rule.id,
        "rule_key": rule.rule_key,
        "rule_name": rule.rule_name,
        "name": rule.rule_name,  # Backward compatibility
        "criteria_set": rule.criteria_set,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "threshold_value": float(rule.threshold_value) if rule.threshold_value else None,
        "description": rule.description,
        "action": rule.action,
        "last_updated": rule.last_updated.isoformat(),
        # threshold_value and severity mirror the literals hardcoded in each rule
        # function — the engine does NOT read these columns (verified 2026-06-21).
        # They are reference/documentation only; the UI should render them
        # read-only. Only is_active actually drives the engine (disable toggle).
        "code_managed_fields": ["threshold_value", "severity"],
    }
    
    if include_full:
        basic.update({
            "implementation_notes": rule.implementation_notes,
            "category": rule.category,
            "example_case": rule.example_case,
            "rejection_message": rule.rejection_message,
            "flag_message": rule.flag_message,
            "is_creditor_specific": rule.is_creditor_specific,
            "applies_to_creditors": rule.applies_to_creditors or [],
            "references": rule.references or [],
            "execution_order": rule.execution_order,
            "depends_on_rules": rule.depends_on_rules or [],
            "related_rules": rule.related_rules or [],
            "last_reviewed": rule.last_reviewed.isoformat() if rule.last_reviewed else None,
            "review_notes": rule.review_notes,
        })
    
    return basic


class RulesListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        include_full = request.query_params.get('include', '').lower() == 'full'

        # Apply filters
        queryset = GlobalCriteria.objects.all()

        # Filter by criteria_set
        criteria_set = request.query_params.get('criteria_set')
        if criteria_set:
            queryset = queryset.filter(criteria_set=criteria_set)

        # Filter by severity
        severity = request.query_params.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by category
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Filter by is_active
        is_active = request.query_params.get('is_active')
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Search by rule_key or rule_name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(rule_key__icontains=search) | Q(rule_name__icontains=search)
            )

        queryset = filter_by_department(
            queryset, GlobalCriteria, request.user,
            DepartmentRuleVisibility, 'rule_key',
        )

        queryset = queryset.order_by('criteria_set', 'rule_key')

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_rule_obj_to_dict(r, include_full=include_full) for r in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['rule_key', 'rule_name', 'criteria_set', 'severity']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if GlobalCriteria.objects.filter(rule_key=data['rule_key']).exists():
            return Response({"detail": "A rule with this rule_key already exists."}, status=status.HTTP_400_BAD_REQUEST)

        rule = GlobalCriteria(
            rule_key=data['rule_key'],
            rule_name=data['rule_name'],
            criteria_set=data['criteria_set'],
            severity=data['severity'],
            is_active=data.get('is_active', True),
            threshold_value=data.get('threshold_value'),
            description=data.get('description'),
            implementation_notes=data.get('implementation_notes'),
            category=data.get('category'),
            example_case=data.get('example_case'),
            rejection_message=data.get('rejection_message'),
            flag_message=data.get('flag_message'),
            is_creditor_specific=data.get('is_creditor_specific', False),
            applies_to_creditors=data.get('applies_to_creditors'),
            references=data.get('references'),
            execution_order=data.get('execution_order'),
            depends_on_rules=data.get('depends_on_rules'),
            related_rules=data.get('related_rules'),
            last_reviewed=data.get('last_reviewed'),
            review_notes=data.get('review_notes'),
            updated_by=request.user,
        )

        try:
            rule.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        rule.save()
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_201_CREATED)


class RulesDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'global_rules'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, rule_key):
        try:
            return GlobalCriteria.objects.get(rule_key=rule_key)
        except GlobalCriteria.DoesNotExist:
            return None

    def get(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_200_OK)

    def put(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # is_active is the ONLY field that drives the engine (disable toggle).
        if 'is_active' in request.data:
            rule.is_active = request.data['is_active']

        # threshold_value and severity are CODE-MANAGED: the engine uses the
        # literals hardcoded in each rule function, not these columns (verified
        # 2026-06-21). Editing them here used to silently no-op. We now allow an
        # unchanged value (so the edit form can still save is_active/docs) but
        # reject an actual change rather than pretend it took effect.
        if 'threshold_value' in request.data:
            incoming = request.data['threshold_value']
            current = float(rule.threshold_value) if rule.threshold_value is not None else None
            incoming_f = float(incoming) if incoming is not None else None
            if incoming_f != current:
                return Response(
                    {"detail": "threshold_value is code-managed and cannot be edited here. "
                               "It mirrors the literal used by the rule engine; change it in "
                               "the rule function (and re-verify)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if 'severity' in request.data and request.data['severity'] != rule.severity:
            return Response(
                {"detail": "severity is code-managed and cannot be edited here. "
                           "It mirrors the rule engine's behaviour for this rule."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if 'rule_name' in request.data:
            rule.rule_name = request.data['rule_name']
        if 'criteria_set' in request.data:
            rule.criteria_set = request.data['criteria_set']

        # Update documentation fields
        if 'description' in request.data:
            rule.description = request.data['description']
        if 'implementation_notes' in request.data:
            rule.implementation_notes = request.data['implementation_notes']
        if 'example_case' in request.data:
            rule.example_case = request.data['example_case']
        if 'rejection_message' in request.data:
            rule.rejection_message = request.data['rejection_message']
        if 'flag_message' in request.data:
            rule.flag_message = request.data['flag_message']

        # Update organization fields
        if 'category' in request.data:
            rule.category = request.data['category']
        if 'is_creditor_specific' in request.data:
            rule.is_creditor_specific = request.data['is_creditor_specific']
        if 'applies_to_creditors' in request.data:
            rule.applies_to_creditors = request.data['applies_to_creditors']
        if 'execution_order' in request.data:
            rule.execution_order = request.data['execution_order']

        # Update reference fields
        if 'references' in request.data:
            rule.references = request.data['references']
        if 'related_rules' in request.data:
            rule.related_rules = request.data['related_rules']
        if 'depends_on_rules' in request.data:
            rule.depends_on_rules = request.data['depends_on_rules']

        # Update review fields
        if 'last_reviewed' in request.data:
            val = request.data['last_reviewed']
            rule.last_reviewed = val if val else None
        if 'review_notes' in request.data:
            rule.review_notes = request.data['review_notes']

        rule.updated_by = request.user
        rule.save()
        return Response(_rule_obj_to_dict(rule, include_full=True), status=status.HTTP_200_OK)

    def delete(self, request, rule_key):
        rule = self._get_object(rule_key)
        if rule is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleHistoryView(APIView):
    """
    Returns trigger history for a single rule_key.
    Queries CriteriaDecision.decision_output JSON to find
    how many times a rule was triggered and when last.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, rule_key):
        from debt_app.models import CriteriaDecision
        from django.utils import timezone
        from datetime import timedelta

        thirty_days_ago = timezone.now() - timedelta(days=30)

        all_decisions = CriteriaDecision.objects.all().order_by(
            '-triggered_at'
        )

        last_triggered = None
        count_30d = 0
        latest_case_id = None

        for decision in all_decisions:
            output = decision.decision_output or {}

            all_rules = (
                output.get('hard_blocks', []) +
                output.get('flags', []) +
                output.get('passed', []) +
                output.get('info', [])
            )

            rule_found = any(
                r.get('rule_id') == rule_key and r.get('triggered')
                for r in all_rules
            )

            if rule_found:
                if last_triggered is None:
                    last_triggered = decision.triggered_at
                    latest_case_id = decision.application_id
                if decision.triggered_at >= thirty_days_ago:
                    count_30d += 1

        return Response({
            "rule_key": rule_key,
            "last_triggered": last_triggered.isoformat()
                if last_triggered else None,
            "times_triggered_30d": count_30d,
            "latest_case_id": latest_case_id,
        })
