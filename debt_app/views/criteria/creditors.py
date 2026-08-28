"""Creditor CRUD, recorded outcomes and the per-creditor audit log."""

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.integrations.aryza import fetch_case_by_reference
from debt_app.integrations.aryza import AryzaCaseNotFoundError
from debt_app.integrations.aryza import AryzaConnectionError
from debt_app.integrations.aryza import AryaTimeoutError
from debt_app.integrations.aryza import AryzaDataError
from debt_app.models import CreditorCriteria
from debt_app.helpers import filter_by_department
from debt_app.permissions import HasWritePermission
from debt_app.permissions import HasReadPermission
from debt_app.models import DepartmentCreditorVisibility
from debt_app.models import CreditorOutcome
from debt_app.models import CriteriaAuditLog

def _creditor_to_dict(creditor):
    return {
        "id": creditor.id,
        "creditor_name": creditor.creditor_name,
        "trading_names": creditor.trading_names,
        "representative": creditor.representative,
        "status": creditor.status,
        "min_dividend_pence": creditor.min_dividend_pence,
        "dividend_notes": creditor.dividend_notes,
        "contact_name": creditor.contact_name,
        "contact_email": creditor.contact_email,
        "contact_phone": creditor.contact_phone,
        "criteria_notes": creditor.criteria_notes,
        "raw_updated_criteria": creditor.raw_updated_criteria,
        "source_sheet": creditor.source_sheet,
        "is_active": creditor.is_active,
        "blocked_until_cleared": creditor.blocked_until_cleared,
        "blocked_reason": creditor.blocked_reason,
        "parent_group": creditor.parent_group,
        "account_age_months": creditor.account_age_months,
        "reject_if_in_dmp": creditor.reject_if_in_dmp,
        "reject_if_never_made_payment": creditor.reject_if_never_made_payment,
        "reject_if_ie_doesnt_match_application": creditor.reject_if_ie_doesnt_match_application,
        "reject_if_debt_repayable_within_months": creditor.reject_if_debt_repayable_within_months,
        "reject_if_client_still_has_asset": creditor.reject_if_client_still_has_asset,
        "reject_if_majority_share_exceeds_pct": creditor.reject_if_majority_share_exceeds_pct,
        "reject_if_second_iva": creditor.reject_if_second_iva,
        "reject_if_police_employed": creditor.reject_if_police_employed,
        "reject_if_equity_exceeds_debt": creditor.reject_if_equity_exceeds_debt,
        "reject_if_ccj": creditor.reject_if_ccj,
        "reject_if_aoe": creditor.reject_if_aoe,
        "requires_pg_called_up": creditor.requires_pg_called_up,
        "requires_arrangement_call_before_proposing": creditor.requires_arrangement_call_before_proposing,
        "requires_grant_overpayment_only": creditor.requires_grant_overpayment_only,
        "vehicle_arrears_repossession_months": creditor.vehicle_arrears_repossession_months,
        "fees_cap_percentage": creditor.fees_cap_percentage,
        "min_di_for_fees_pence": creditor.min_di_for_fees_pence,
        "termination_risk_if_vehicle_on_finance": creditor.termination_risk_if_vehicle_on_finance,
        "conditional_voter": creditor.conditional_voter,
        "conditional_voter_min_dividend_pence": creditor.conditional_voter_min_dividend_pence,
        "open_banking_access": creditor.open_banking_access,
        "fraud_claim_risk": creditor.fraud_claim_risk,
        "last_reviewed": creditor.last_reviewed.isoformat() if creditor.last_reviewed else None,
        "last_updated": creditor.last_updated.isoformat(),
    }


_CREDITOR_WRITABLE_FIELDS = [
    'creditor_name', 'trading_names', 'representative', 'status',
    'min_dividend_pence', 'dividend_notes', 'contact_name', 'contact_email', 'contact_phone',
    'criteria_notes', 'raw_updated_criteria', 'source_sheet',
    'is_active', 'account_age_months', 'parent_group',
    'reject_if_in_dmp', 'reject_if_never_made_payment',
    'reject_if_ie_doesnt_match_application', 'reject_if_debt_repayable_within_months',
    'reject_if_client_still_has_asset', 'reject_if_majority_share_exceeds_pct',
    'reject_if_second_iva', 'reject_if_police_employed', 'reject_if_equity_exceeds_debt',
    'reject_if_ccj', 'reject_if_aoe',
    'requires_pg_called_up', 'requires_arrangement_call_before_proposing',
    'requires_grant_overpayment_only', 'vehicle_arrears_repossession_months',
    'fees_cap_percentage', 'min_di_for_fees_pence',
    'termination_risk_if_vehicle_on_finance', 'conditional_voter',
    'conditional_voter_min_dividend_pence', 'open_banking_access', 'fraud_claim_risk',
    'blocked_until_cleared', 'blocked_reason', 'last_reviewed',
]


class CreditorListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        search = request.query_params.get('search', '')
        representative = request.query_params.get('representative', '')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)

        queryset = CreditorCriteria.objects.all().order_by('creditor_name')

        if search:
            queryset = queryset.filter(
                Q(creditor_name__icontains=search) |
                Q(trading_names__icontains=search)
            )

        if representative:
            queryset = queryset.filter(representative=representative)

        queryset = filter_by_department(
            queryset, CreditorCriteria, request.user,
            DepartmentCreditorVisibility, 'creditor',
        )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_creditor_to_dict(c) for c in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['creditor_name']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if CreditorCriteria.objects.filter(creditor_name=data['creditor_name']).exists():
            return Response({"detail": "A creditor with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

        creditor = CreditorCriteria()
        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in data:
                setattr(creditor, field, data[field])
        creditor.updated_by = request.user

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        creditor.save()
        return Response(_creditor_to_dict(creditor), status=status.HTTP_201_CREATED)


class CreditorDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, id):
        try:
            return CreditorCriteria.objects.get(id=id)
        except CreditorCriteria.DoesNotExist:
            return None

    def get(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_creditor_to_dict(creditor), status=status.HTTP_200_OK)

    def put(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Snapshot old values before mutation for audit trail
        _old = {
            field: str(getattr(creditor, field, ''))
            for field in _CREDITOR_WRITABLE_FIELDS
            if field in request.data
        }

        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in request.data:
                setattr(creditor, field, request.data[field])

        try:
            creditor.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Audit trail — log every changed field
        for field in _CREDITOR_WRITABLE_FIELDS:
            if field in request.data:
                old_val = _old[field]
                new_val = str(request.data[field])
                if old_val != new_val:
                    CriteriaAuditLog.objects.create(
                        creditor=creditor,
                        changed_by=request.user,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        action='update',
                    )

        creditor.updated_by = request.user
        creditor.save()
        return Response(_creditor_to_dict(creditor), status=status.HTTP_200_OK)

    def delete(self, request, id):
        creditor = self._get_object(id)
        if creditor is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        creditor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreditorOutcomeListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'general_creditors'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        outcomes = creditor.outcomes.select_related('submitted_by').all()
        approved = outcomes.filter(outcome='approved').count()
        disapproved = outcomes.filter(outcome='disapproved').count()

        return Response({
            "tally": {
                "approved": approved,
                "disapproved": disapproved,
                "total": approved + disapproved,
            },
            "outcomes": [
                {
                    "id": o.id,
                    "case_reference": o.case_reference,
                    "outcome": o.outcome,
                    "outcome_date": o.outcome_date,
                    "comment": o.comment,
                    "submitted_by": o.submitted_by.get_full_name() or o.submitted_by.username if o.submitted_by else None,
                    "submitted_at": o.submitted_at,
                }
                for o in outcomes
            ]
        })

    def post(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        case_reference = request.data.get("case_reference", "").strip()
        outcome = request.data.get("outcome", "").strip()
        outcome_date = request.data.get("outcome_date")
        comment = request.data.get("comment", "").strip()

        if not case_reference:
            return Response({"detail": "case_reference is required."}, status=status.HTTP_400_BAD_REQUEST)
        if outcome not in ('approved', 'disapproved'):
            return Response({"detail": "outcome must be 'approved' or 'disapproved'."}, status=status.HTTP_400_BAD_REQUEST)
        if not outcome_date:
            return Response({"detail": "outcome_date is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate the case reference exists in Aryza before saving
        try:
            fetch_case_by_reference(case_reference)
        except AryzaCaseNotFoundError:
            return Response(
                {
                    "detail": f"Case reference '{case_reference}' was not found in Aryza. "
                              "Please check the reference and try again.",
                    "field": "case_reference",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (AryzaConnectionError, AryaTimeoutError, AryzaDataError, Exception):
            return Response(
                {
                    "detail": "Unable to validate case reference against Aryza. Please try again.",
                    "field": "case_reference",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        outcome_obj = CreditorOutcome.objects.create(
            creditor=creditor,
            case_reference=case_reference,
            outcome=outcome,
            outcome_date=outcome_date,
            comment=comment,
            submitted_by=request.user,
        )

        return Response({
            "id": outcome_obj.id,
            "case_reference": outcome_obj.case_reference,
            "outcome": outcome_obj.outcome,
            "outcome_date": outcome_obj.outcome_date,
            "comment": outcome_obj.comment,
            "submitted_by": request.user.get_full_name() or request.user.username,
            "submitted_at": outcome_obj.submitted_at,
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, id):
        outcome_id = request.data.get("outcome_id")
        if not outcome_id:
            return Response({"detail": "outcome_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        outcome = CreditorOutcome.objects.filter(id=outcome_id, creditor__id=id).first()
        if not outcome:
            return Response({"detail": "Outcome not found."}, status=status.HTTP_404_NOT_FOUND)

        outcome.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreditorAuditLogView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasReadPermission]
    required_feature = 'general_creditors'

    def get(self, request, id):
        creditor = CreditorCriteria.objects.filter(id=id).first()
        if not creditor:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        logs = creditor.audit_logs.select_related('changed_by').order_by('-changed_at')

        return Response([
            {
                "id": log.id,
                "field_name": log.field_name,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "action": log.action,
                "changed_by": log.changed_by.get_full_name() or log.changed_by.username if log.changed_by else None,
                "changed_at": log.changed_at,
            }
            for log in logs
        ])
