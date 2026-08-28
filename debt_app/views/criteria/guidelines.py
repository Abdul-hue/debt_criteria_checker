"""SFS expenditure guidelines and their categories (JWT-authenticated).

The token-free service-to-service equivalents live in ``views/internal_sfs.py``."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.helpers import get_user_department
from debt_app.helpers import filter_by_department
from debt_app.permissions import HasFeatureAccess
from debt_app.permissions import HasWritePermission
from debt_app.permissions import HasReadPermission
from debt_app.models import GuidelineCategory
from debt_app.models import ExpenditureGuideline
from debt_app.models import DepartmentSFSVisibility

from debt_app.views.criteria._shared import (
    error_response,
)

def _guideline_to_dict(g) -> dict:
    return {
        "id": g.id,
        "category": g.category,
        "label": g.label,
        "category_group": g.category_group_id,
        "max": g.max,
        "min": g.min,
        "sort_order": g.sort_order,
        "adult_1": float(g.adult_1),
        "adult_2": float(g.adult_2),
        "adult_1_child_1": float(g.adult_1_child_1),
        "adult_1_child_2": float(g.adult_1_child_2),
        "adult_1_child_3": float(g.adult_1_child_3),
        "adult_1_child_4": float(g.adult_1_child_4),
        "adult_1_child_5": float(g.adult_1_child_5),
        "adult_2_child_1": float(g.adult_2_child_1),
        "adult_2_child_2": float(g.adult_2_child_2),
        "adult_2_child_3": float(g.adult_2_child_3),
        "adult_2_child_4": float(g.adult_2_child_4),
        "adult_2_child_5": float(g.adult_2_child_5),
        "per_child": float(g.per_child),
        "per_vehicle": float(g.per_vehicle),
        "per_vehicle_max": float(g.per_vehicle_max),
        "first_adult": float(g.first_adult),
        "additional_adult": float(g.additional_adult),
        "child_under_16": float(g.child_under_16),
        "child_16_18": float(g.child_16_18),
        "watch_per_adult": float(g.watch_per_adult),
        "non_watch_per_adult": float(g.non_watch_per_adult),
        "watch_per_vehicle": float(g.watch_per_vehicle),
        "non_watch_per_vehicle": float(g.non_watch_per_vehicle),
        "one_adult_cap": float(g.one_adult_cap),
        "two_adults_cap": float(g.two_adults_cap),
        "formula": g.formula,
        "below_action": g.below_action,
        "above_action": g.above_action,
        "mismatch_action": g.mismatch_action,
        "notes": g.notes,
        "aryza_aliases": g.aryza_aliases,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


def _guideline_category_to_dict(cat, include_guidelines=False) -> dict:
    d = {
        "id": cat.id,
        "name": cat.name,
        "upper_cap": float(cat.upper_cap) if cat.upper_cap is not None else None,
        "sort_order": cat.sort_order,
    }
    if include_guidelines:
        d["guidelines"] = [_guideline_to_dict(g) for g in cat.guidelines.all()]
    return d


class ExpenditureGuidelineCategoryListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasFeatureAccess()]
        return [IsAdminUser()]

    def get(self, request):
        qs = GuidelineCategory.objects.prefetch_related('guidelines').order_by('sort_order', 'name')

        # For non-admins, filter nested guidelines by department visibility
        if not request.user.is_staff:
            from debt_app.helpers import get_user_department
            dept = get_user_department(request.user)
            results = []
            for cat in qs:
                guidelines_qs = filter_by_department(
                    cat.guidelines.all(), ExpenditureGuideline, request.user,
                    DepartmentSFSVisibility, 'guideline',
                )
                cat_dict = _guideline_category_to_dict(cat)
                cat_dict['guidelines'] = [_guideline_to_dict(g) for g in guidelines_qs]
                results.append(cat_dict)
            return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)

        return Response({
            "count": qs.count(),
            "results": [_guideline_category_to_dict(c, include_guidelines=True) for c in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        name = data.get('name', '').strip()
        if not name:
            return error_response("name is required", "MISSING_NAME", status.HTTP_400_BAD_REQUEST)
        cat = GuidelineCategory.objects.create(
            name=name,
            upper_cap=data.get('upper_cap') or None,
            sort_order=int(data.get('sort_order', 0)),
        )
        return Response(_guideline_category_to_dict(cat), status=status.HTTP_201_CREATED)


class ExpenditureGuidelineCategoryDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

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
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        data = request.data
        if 'name' in data:
            cat.name = data['name']
        if 'upper_cap' in data:
            cat.upper_cap = data['upper_cap'] or None
        if 'sort_order' in data:
            cat.sort_order = int(data['sort_order'])
        cat.save()
        return Response(_guideline_category_to_dict(cat, include_guidelines=True), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        cat = self._get_object(pk)
        if cat is None:
            return error_response("Category not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        cat.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExpenditureGuidelineListView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def get(self, request):
        qs = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order', 'category'
        )
        category_filter = request.query_params.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)

        qs = filter_by_department(
            qs, ExpenditureGuideline, request.user,
            DepartmentSFSVisibility, 'guideline',
        )

        return Response({
            "count": qs.count(),
            "results": [_guideline_to_dict(g) for g in qs],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        category = data.get('category', '').strip()
        label = data.get('label', '').strip()
        if not category:
            return error_response("category is required", "MISSING_CATEGORY", status.HTTP_400_BAD_REQUEST)
        if not label:
            return error_response("label is required", "MISSING_LABEL", status.HTTP_400_BAD_REQUEST)
        if ExpenditureGuideline.objects.filter(category=category).exists():
            return error_response("A guideline with this category already exists", "DUPLICATE_CATEGORY", status.HTTP_400_BAD_REQUEST)

        category_group = None
        if data.get('category_group'):
            try:
                category_group = GuidelineCategory.objects.get(pk=data['category_group'])
            except GuidelineCategory.DoesNotExist:
                return error_response("category_group not found", "INVALID_CATEGORY_GROUP", status.HTTP_400_BAD_REQUEST)

        decimal_fields = [
            'adult_1', 'adult_2',
            'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
            'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
            'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
            'child_under_16', 'child_16_18',
            'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
            'one_adult_cap', 'two_adults_cap',
        ]
        kwargs = {
            'category': category,
            'label': label,
            'category_group': category_group,
            'max': bool(data.get('max', False)),
            'min': bool(data.get('min', False)),
            'sort_order': int(data.get('sort_order', 0)),
            'formula': data.get('formula', ''),
            'below_action': data.get('below_action', ''),
            'above_action': data.get('above_action', ''),
            'mismatch_action': data.get('mismatch_action', ''),
            'notes': data.get('notes', ''),
            'aryza_aliases': data.get('aryza_aliases', ''),
        }
        for f in decimal_fields:
            kwargs[f] = data.get(f, 0) or 0

        g = ExpenditureGuideline.objects.create(**kwargs)
        return Response(_guideline_to_dict(g), status=status.HTTP_201_CREATED)


class ExpenditureGuidelineDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    required_feature = 'sfs_guidelines'

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasReadPermission()]
        return [IsAuthenticated(), HasWritePermission()]

    def _get_object(self, pk):
        try:
            return ExpenditureGuideline.objects.select_related('category_group').get(pk=pk)
        except ExpenditureGuideline.DoesNotExist:
            return None

    def get(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def patch(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        data = request.data
        updatable = [
            'label', 'max', 'min', 'sort_order', 'formula',
            'below_action', 'above_action', 'mismatch_action', 'notes', 'aryza_aliases',
            'adult_1', 'adult_2',
            'adult_1_child_1', 'adult_1_child_2', 'adult_1_child_3', 'adult_1_child_4', 'adult_1_child_5',
            'adult_2_child_1', 'adult_2_child_2', 'adult_2_child_3', 'adult_2_child_4', 'adult_2_child_5',
            'per_child', 'per_vehicle', 'per_vehicle_max', 'first_adult', 'additional_adult',
            'child_under_16', 'child_16_18',
            'watch_per_adult', 'non_watch_per_adult', 'watch_per_vehicle', 'non_watch_per_vehicle',
            'one_adult_cap', 'two_adults_cap',
        ]
        for field in updatable:
            if field in data:
                setattr(g, field, data[field])
        if 'category_group' in data:
            if data['category_group'] is None:
                g.category_group = None
            else:
                try:
                    g.category_group = GuidelineCategory.objects.get(pk=data['category_group'])
                except GuidelineCategory.DoesNotExist:
                    return error_response("category_group not found", "INVALID_CATEGORY_GROUP", status.HTTP_400_BAD_REQUEST)
        g.save()
        return Response(_guideline_to_dict(g), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        g = self._get_object(pk)
        if g is None:
            return error_response("Guideline not found", "NOT_FOUND", status.HTTP_404_NOT_FOUND)
        g.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
