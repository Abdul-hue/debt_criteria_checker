"""
Token-free SFS guideline endpoints for service-to-service callers.

The case-assessment (CA) backend runs on the same server as this microservice
and already calls /api/v1/assess/ with no JWT. These endpoints follow that
same pattern for the SFS expenditure guidelines so CA does not have to obtain,
cache and refresh a token just to read reference data.

Deliberately separate from the JWT-protected /api/v1/criteria/sfs/* routes the
admin UI uses — those keep their department-visibility filtering and feature
permissions untouched. These internal routes return the FULL guideline set,
because a service-to-service caller has no department.

Reads are fully open (like /api/v1/assess/). Writes are restricted to callers
on the server itself (INTERNAL_API_ALLOWED_IPS) so an unauthenticated POST /
PATCH / DELETE is not exposed to the wider network.
"""

from django.conf import settings as django_settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from debt_app.models import ExpenditureGuideline, GuidelineCategory
from debt_app.views.criteria_views import (
    _guideline_to_dict,
    _guideline_category_to_dict,
    error_response,
)

# Numeric guideline amounts — writable on create and update.
GUIDELINE_DECIMAL_FIELDS = (
    'adult_1', 'adult_2',
    'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
    'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
    'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
    'child_under_16', 'child_16_18',
    'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
    'one_adult_cap', 'two_adults_cap',
)

# Text / flag fields — writable on create and update. `category` is create-only:
# it is the stable key the engine matches Aryza expenditure rows against.
GUIDELINE_TEXT_FIELDS = (
    'label', 'formula', 'below_action', 'above_action', 'mismatch_action',
    'notes', 'aryza_aliases',
)

DEFAULT_ALLOWED_WRITE_IPS = ('127.0.0.1', '::1')


def _client_ip(request) -> str:
    """
    Caller IP for the write guard.

    REMOTE_ADDR is the only value a client cannot forge, so it is what we
    authorise on. X-Forwarded-For is honoured ONLY when the connection itself
    comes from a proxy we listed in INTERNAL_API_TRUSTED_PROXIES — otherwise
    any caller could send 'X-Forwarded-For: 127.0.0.1' and walk through the
    guard. When a trusted proxy is in front, the LAST entry is the hop that
    proxy appended; earlier entries are client-supplied and unreliable.
    """
    remote = request.META.get('REMOTE_ADDR', '') or ''
    trusted = getattr(django_settings, 'INTERNAL_API_TRUSTED_PROXIES', ())
    if remote and remote in trusted:
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[-1].strip()
    return remote


def _write_blocked(request):
    """
    Returns an error Response when this caller may not mutate, else None.

    Set INTERNAL_API_ALLOWED_IPS=* in the environment to allow writes from
    anywhere (only sensible on a closed network).
    """
    allowed = getattr(django_settings, 'INTERNAL_API_ALLOWED_IPS', DEFAULT_ALLOWED_WRITE_IPS)
    if '*' in allowed:
        return None
    ip = _client_ip(request)
    if ip in allowed:
        return None
    return error_response(
        f"Writes to the internal SFS API are only accepted from the server itself "
        f"(caller: {ip or 'unknown'}). Use the JWT-authenticated "
        f"/api/v1/criteria/sfs/ routes, or add this IP to INTERNAL_API_ALLOWED_IPS.",
        "WRITE_NOT_ALLOWED_FROM_HOST",
        status.HTTP_403_FORBIDDEN,
    )


def _apply_guideline_fields(g, data):
    """Copy writable fields from a request body onto a guideline instance."""
    for f in GUIDELINE_TEXT_FIELDS:
        if f in data:
            setattr(g, f, data[f] if data[f] is not None else '')
    for f in ('max', 'min'):
        if f in data:
            setattr(g, f, bool(data[f]))
    if 'sort_order' in data:
        g.sort_order = int(data['sort_order'] or 0)
    for f in GUIDELINE_DECIMAL_FIELDS:
        if f in data:
            setattr(g, f, data[f] or 0)
    return g


def _resolve_category_group(data):
    """
    Returns (category_group, error_response). category_group is None both when
    the caller omitted the field and when they explicitly cleared it — callers
    should only assign when 'category_group' is actually present in the body.
    """
    if not data.get('category_group'):
        return None, None
    try:
        return GuidelineCategory.objects.get(pk=data['category_group']), None
    except (GuidelineCategory.DoesNotExist, ValueError, TypeError):
        return None, error_response(
            "category_group not found", "INVALID_CATEGORY_GROUP",
            status.HTTP_400_BAD_REQUEST,
        )


class _OpenAPIView(APIView):
    """No JWT, no session — same posture as DirectAssessView."""
    authentication_classes = []
    permission_classes = [AllowAny]


class InternalGuidelineListView(_OpenAPIView):
    """
    GET  /api/v1/criteria/internal/sfs/guidelines/       — full guideline set
    POST /api/v1/criteria/internal/sfs/guidelines/       — create one
    """

    def get(self, request):
        qs = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order', 'category'
        )
        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        group = request.query_params.get('category_group')
        if group:
            qs = qs.filter(category_group_id=group)

        return Response({
            "count": qs.count(),
            "results": [_guideline_to_dict(g) for g in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        data = request.data
        category = (data.get('category') or '').strip()
        label = (data.get('label') or '').strip()
        if not category:
            return error_response("category is required", "MISSING_CATEGORY", status.HTTP_400_BAD_REQUEST)
        if not label:
            return error_response("label is required", "MISSING_LABEL", status.HTTP_400_BAD_REQUEST)
        if ExpenditureGuideline.objects.filter(category=category).exists():
            return error_response(
                "A guideline with this category already exists",
                "DUPLICATE_CATEGORY", status.HTTP_400_BAD_REQUEST,
            )

        category_group, err = _resolve_category_group(data)
        if err:
            return err

        g = ExpenditureGuideline(category=category, category_group=category_group)
        _apply_guideline_fields(g, data)
        g.save()
        return Response(_guideline_to_dict(g), status=status.HTTP_201_CREATED)


class InternalGuidelineDetailView(_OpenAPIView):
    """
    GET    /api/v1/criteria/internal/sfs/guidelines/<pk>/
    PATCH  /api/v1/criteria/internal/sfs/guidelines/<pk>/
    DELETE /api/v1/criteria/internal/sfs/guidelines/<pk>/
    """

    lookup_by_category = False

    def _get_object(self, key):
        qs = ExpenditureGuideline.objects.select_related('category_group')
        try:
            if self.lookup_by_category:
                return qs.get(category=key)
            return qs.get(pk=key)
        except ExpenditureGuideline.DoesNotExist:
            return None

    def get(self, request, key):
        g = self._get_object(key)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def patch(self, request, key):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        g = self._get_object(key)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'category_group' in data:
            if data['category_group'] is None:
                g.category_group = None
            else:
                category_group, err = _resolve_category_group(data)
                if err:
                    return err
                g.category_group = category_group
        _apply_guideline_fields(g, data)
        g.save()
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def delete(self, request, key):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        g = self._get_object(key)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        g.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InternalGuidelineByCategoryView(InternalGuidelineDetailView):
    """Same CRUD, addressed by the `category` slug instead of the numeric id."""
    lookup_by_category = True


class InternalGuidelineCategoryListView(_OpenAPIView):
    """
    GET  /api/v1/criteria/internal/sfs/categories/   — groups + nested guidelines
    POST /api/v1/criteria/internal/sfs/categories/
    """

    def get(self, request):
        qs = GuidelineCategory.objects.prefetch_related('guidelines').order_by('sort_order', 'name')
        return Response({
            "count": qs.count(),
            "results": [_guideline_category_to_dict(c, include_guidelines=True) for c in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        name = (request.data.get('name') or '').strip()
        if not name:
            return error_response("name is required", "MISSING_NAME", status.HTTP_400_BAD_REQUEST)
        cat = GuidelineCategory.objects.create(
            name=name,
            upper_cap=request.data.get('upper_cap') or None,
            sort_order=int(request.data.get('sort_order') or 0),
        )
        return Response(_guideline_category_to_dict(cat), status=status.HTTP_201_CREATED)


class InternalGuidelineCategoryDetailView(_OpenAPIView):
    """
    GET    /api/v1/criteria/internal/sfs/categories/<pk>/
    PATCH  /api/v1/criteria/internal/sfs/categories/<pk>/
    DELETE /api/v1/criteria/internal/sfs/categories/<pk>/
    """

    def _get_object(self, pk):
        try:
            return GuidelineCategory.objects.prefetch_related('guidelines').get(pk=pk)
        except GuidelineCategory.DoesNotExist:
            return None

    def get(self, request, pk):
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        return Response(_guideline_category_to_dict(cat, include_guidelines=True), status=status.HTTP_200_OK)

    def patch(self, request, pk):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        data = request.data
        if 'name' in data:
            cat.name = data['name']
        if 'upper_cap' in data:
            cat.upper_cap = data['upper_cap'] or None
        if 'sort_order' in data:
            cat.sort_order = int(data['sort_order'] or 0)
        cat.save()
        return Response(_guideline_category_to_dict(cat, include_guidelines=True), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        blocked = _write_blocked(request)
        if blocked:
            return blocked

        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        cat.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
