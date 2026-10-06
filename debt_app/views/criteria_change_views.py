"""
Controlled criteria change endpoints (Draft -> Trial -> Sign-off -> Live).

  GET  criteria-changes/                     list (criteria_changes or criteria_approval)
  POST criteria-changes/                     draft a change           (criteria_changes)
  GET  criteria-changes/managed-fields/      what the workflow can change
  GET  criteria-changes/<id>/                detail
  POST criteria-changes/<id>/trial/          trial on an isolated copy (criteria_changes)
  POST criteria-changes/<id>/approve/        second-manager sign-off -> live (criteria_approval)
  POST criteria-changes/<id>/reject/         second-manager rejection (criteria_approval)
  POST criteria-changes/<id>/cancel/         author withdraws          (criteria_changes)
  GET  criteria-versions/                    version history
  GET  criteria-versions/<n>/                version detail + audit entries
  POST criteria-versions/<n>/rollback/       draft a rollback change   (criteria_changes)
"""

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.models import CriteriaChangeRequest, CriteriaVersion
from debt_app.permissions import HasEnabledFeature, user_has_enabled_feature
from debt_app.services import criteria_versioning as cv

_AUTH = [JWTAuthentication]


def _err(exc):
    return Response({"success": False, "error": exc.message, "code": exc.code}, status=exc.status_code)


def _user(u):
    return u.get_username() if u else None


def _change_dict(c, full=False, viewer=None):
    d = {
        "id": c.pk,
        "title": c.title,
        "reason": c.reason,
        "status": c.status,
        "status_label": c.get_status_display(),
        "is_rollback": c.is_rollback,
        "rollback_to_version": c.rollback_to_version.number if c.rollback_to_version_id else None,
        "items": c.items,
        "created_by": _user(c.created_by),
        "created_at": c.created_at.isoformat(),
        "trial_run_by": _user(c.trial_run_by),
        "trial_run_at": c.trial_run_at.isoformat() if c.trial_run_at else None,
        "decided_by": _user(c.decided_by),
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "decision_note": c.decision_note,
        "applied_version": c.applied_version.number if c.applied_version_id else None,
    }
    if viewer is not None:
        is_author = c.created_by_id == viewer.pk
        is_open = c.status in (CriteriaChangeRequest.STATUS_DRAFT, CriteriaChangeRequest.STATUS_TRIALLED)
        d["viewer"] = {
            "is_author": is_author,
            "can_trial": is_open and user_has_enabled_feature(viewer, "criteria_changes"),
            "can_approve": (c.status == CriteriaChangeRequest.STATUS_TRIALLED and not is_author
                            and user_has_enabled_feature(viewer, "criteria_approval")),
            "can_reject": is_open and not is_author and user_has_enabled_feature(viewer, "criteria_approval"),
            "can_cancel": is_open and (is_author or viewer.is_staff),
        }
    if c.trial_summary:
        s = c.trial_summary
        d["trial_summary"] = s if full else {
            k: s.get(k) for k in ("cases_evaluated", "cases_changed", "cases_errored", "case_limit")
        }
    return d


def _version_dict(v, full=False):
    d = {
        "number": v.number,
        "label": v.label,
        "created_at": v.created_at.isoformat(),
        "created_by": _user(v.created_by),
        "change_request": v.change_request_id,
        "note": v.note,
        "fingerprint": v.fingerprint,
        "code_version": v.code_version,
    }
    if full:
        d["audit"] = [
            {
                "model": a.model, "object_id": a.object_id, "object_label": a.object_label,
                "field": a.field, "old_value": a.old_value, "new_value": a.new_value,
                "proposed_by": _user(a.proposed_by), "approved_by": _user(a.approved_by),
                "applied_at": a.applied_at.isoformat(), "code_version": a.code_version,
            }
            for a in v.audit_entries.select_related("proposed_by", "approved_by").order_by("id")
        ]
    return d


def _can_view(user):
    return user_has_enabled_feature(user, "criteria_changes") or user_has_enabled_feature(user, "criteria_approval")


def _get_change(pk):
    return CriteriaChangeRequest.objects.select_related(
        "created_by", "trial_run_by", "decided_by", "applied_version", "rollback_to_version",
    ).filter(pk=pk).first()


class CriteriaChangeListView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = {"POST": "criteria_changes", "GET": "criteria_changes"}

    def check_permissions(self, request):
        if request.method == "GET":
            if not (request.user and request.user.is_authenticated):
                self.permission_denied(request)
            if not _can_view(request.user):
                self.permission_denied(request, message="You do not have access to criteria changes.")
            return
        super().check_permissions(request)

    def get(self, request):
        qs = CriteriaChangeRequest.objects.select_related(
            "created_by", "trial_run_by", "decided_by", "applied_version", "rollback_to_version",
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        live_label, live_fp = cv.current_criteria_version()
        return Response({
            "live_version": live_label,
            "live_fingerprint": live_fp,
            "change_control_enforced": bool(getattr(settings, "CRITERIA_CHANGE_CONTROL_ENFORCED", False)),
            "results": [_change_dict(c) for c in qs[:200]],
        })

    def post(self, request):
        try:
            change = cv.create_change_request(
                request.user, request.data.get("title"), request.data.get("reason"), request.data.get("items"),
            )
        except cv.CriteriaChangeError as exc:
            return _err(exc)
        return Response(_change_dict(change, full=True), status=status.HTTP_201_CREATED)


class CriteriaManagedFieldsView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "criteria_changes"

    def get(self, request):
        return Response({
            "managed_fields": cv.MANAGED_FIELDS,
            "field_info": cv.managed_field_info(),
            "note": ("Only database-held criteria are managed here. Rule logic and hard-coded thresholds "
                     "are changed by developers through code review and deployment."),
        })


class CriteriaChangeDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not _can_view(request.user):
            return Response({"detail": "You do not have access to criteria changes."}, status=403)
        change = _get_change(pk)
        if change is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(_change_dict(change, full=True, viewer=request.user))


class _ChangeActionView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated, HasEnabledFeature]

    def post(self, request, pk):
        change = _get_change(pk)
        if change is None:
            return Response({"detail": "Not found."}, status=404)
        try:
            payload = self.act(request, change)
        except cv.CriteriaChangeError as exc:
            return _err(exc)
        return Response(payload)


class CriteriaChangeTrialView(_ChangeActionView):
    required_feature = "criteria_changes"

    def act(self, request, change):
        cv.run_trial(change, request.user, request.data.get("max_cases"))
        return _change_dict(_get_change(change.pk), full=True)


class CriteriaChangeApproveView(_ChangeActionView):
    required_feature = "criteria_approval"

    def act(self, request, change):
        version = cv.approve_and_apply(change, request.user, request.data.get("note", ""))
        return {"change": _change_dict(_get_change(change.pk), full=True), "version": _version_dict(version)}


class CriteriaChangeRejectView(_ChangeActionView):
    required_feature = "criteria_approval"

    def act(self, request, change):
        cv.reject_change(change, request.user, request.data.get("note", ""))
        return _change_dict(_get_change(change.pk), full=True)


class CriteriaChangeCancelView(_ChangeActionView):
    required_feature = "criteria_changes"

    def act(self, request, change):
        cv.cancel_change_request(change, request.user)
        return _change_dict(_get_change(change.pk), full=True)


class CriteriaVersionListView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can_view(request.user):
            return Response({"detail": "You do not have access to criteria versions."}, status=403)
        live_label, live_fp = cv.current_criteria_version()
        versions = CriteriaVersion.objects.select_related("created_by").order_by("-number")[:200]
        return Response({
            "live_version": live_label,
            "live_fingerprint": live_fp,
            "results": [_version_dict(v) for v in versions],
        })


class CriteriaVersionDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated]

    def get(self, request, number):
        if not _can_view(request.user):
            return Response({"detail": "You do not have access to criteria versions."}, status=403)
        version = CriteriaVersion.objects.select_related("created_by").filter(number=number).first()
        if version is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(_version_dict(version, full=True))


class CriteriaVersionRollbackView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "criteria_changes"

    def post(self, request, number):
        try:
            change = cv.create_rollback_request(request.user, number, request.data.get("reason"))
        except cv.CriteriaChangeError as exc:
            return _err(exc)
        return Response(_change_dict(change, full=True), status=status.HTTP_201_CREATED)


class CriteriaChangeTargetsView(APIView):
    """Find a managed criteria row and read its current managed values, for
    drafting a change. GET ?model=CreditorCriteria&q=bar -> rows;
    GET ?model=CreditorCriteria&id=12 -> that row's managed field values."""

    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated, HasEnabledFeature]
    required_feature = "criteria_changes"

    def get(self, request):
        model_name = request.query_params.get("model")
        if model_name not in cv.MANAGED_MODELS:
            return Response({"success": False, "error": "Unknown criteria table.", "code": "NOT_MANAGED"}, status=400)
        model = cv.MANAGED_MODELS[model_name]
        label_field = cv.LABEL_FIELD[model_name]
        object_id = request.query_params.get("id")
        if object_id:
            obj = model.objects.filter(pk=object_id).first()
            if obj is None:
                return Response({"detail": "Not found."}, status=404)
            return Response({
                "id": obj.pk,
                "label": getattr(obj, label_field),
                "values": {f: cv._json_value(getattr(obj, f)) for f in cv.MANAGED_FIELDS[model_name]},
            })
        q = (request.query_params.get("q") or "").strip()
        qs = model.objects.order_by(label_field)
        if q:
            qs = qs.filter(**{f"{label_field}__icontains": q})
        return Response({"results": [{"id": pk, "label": label} for pk, label in qs.values_list("pk", label_field)[:50]]})
