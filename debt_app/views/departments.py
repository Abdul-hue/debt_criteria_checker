from django.contrib.auth.models import User
from django.utils.text import slugify
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.models import (
    Department,
    UserProfile,
    GlobalCriteria,
    CreditorCriteria,
    CouncilRule,
    ExpenditureGuideline,
    DepartmentRuleVisibility,
    DepartmentCreditorVisibility,
    DepartmentCouncilVisibility,
    DepartmentSFSVisibility,
    DepartmentFeatureAccess,
    DepartmentFeaturePermission,
)
from debt_app.serializers.departments import (
    DepartmentSerializer,
    UserProfileSerializer,
    DepartmentRuleVisibilitySerializer,
    DepartmentCreditorVisibilitySerializer,
    DepartmentCouncilVisibilitySerializer,
)
from debt_app.helpers import get_user_department

_AUTH = [JWTAuthentication]
_ADMIN = [IsAdminUser]


# ---------------------------------------------------------------------------
# Department CRUD
# ---------------------------------------------------------------------------

class DepartmentListView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request):
        qs = Department.objects.all()
        return Response(DepartmentSerializer(qs, many=True).data)

    def post(self, request):
        data = request.data.copy()
        if not data.get('slug') and data.get('name'):
            data['slug'] = slugify(data['name'])
        s = DepartmentSerializer(data=data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=status.HTTP_201_CREATED)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


class DepartmentDetailView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def _get(self, pk):
        try:
            return Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return None

    def get(self, request, pk):
        dept = self._get(pk)
        if dept is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(DepartmentSerializer(dept).data)

    def put(self, request, pk):
        dept = self._get(pk)
        if dept is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        if not data.get('slug') and data.get('name'):
            data['slug'] = slugify(data['name'])
        s = DepartmentSerializer(dept, data=data)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        dept = self._get(pk)
        if dept is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        if not data.get('slug') and data.get('name'):
            data['slug'] = slugify(data['name'])
        s = DepartmentSerializer(dept, data=data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        dept = self._get(pk)
        if dept is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        dept.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# User → Department assignment
# ---------------------------------------------------------------------------

class UserDepartmentView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def _get_user(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            profile = user.profile
            return Response(UserProfileSerializer(profile).data)
        except UserProfile.DoesNotExist:
            return Response({
                "id": None,
                "user": {"id": user.id, "username": user.username, "email": user.email},
                "department": None,
            })

    def put(self, request, pk):
        user = self._get_user(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        department_id = request.data.get('department_id')
        if department_id is None:
            return Response({"detail": "department_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dept = Department.objects.get(pk=department_id)
        except Department.DoesNotExist:
            return Response({"detail": "Department not found."}, status=status.HTTP_404_NOT_FOUND)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.department = dept
        profile.save()
        return Response(UserProfileSerializer(profile).data)


# ---------------------------------------------------------------------------
# Rule visibility
# ---------------------------------------------------------------------------

class DepartmentRulesView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        rules = GlobalCriteria.objects.all().order_by('rule_key')
        # Build a map: rule_key string → is_visible
        vis_map = {
            v.rule_key_id: v.is_visible
            for v in DepartmentRuleVisibility.objects.filter(department=dept)
        }
        result = [
            {
                'rule_key': r.rule_key,
                'rule_name': r.rule_name,
                'criteria_set': r.criteria_set,
                'is_active': r.is_active,
                'is_visible': vis_map.get(r.rule_key, True),
            }
            for r in rules
        ]
        return Response(result)


class DepartmentRulesToggleView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        rule_key = request.data.get('rule_key')
        is_visible = request.data.get('is_visible')

        if not rule_key:
            return Response({"detail": "rule_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        if is_visible is None:
            return Response({"detail": "is_visible is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rule = GlobalCriteria.objects.get(rule_key=rule_key)
        except GlobalCriteria.DoesNotExist:
            return Response({"detail": f"Rule '{rule_key}' not found."}, status=status.HTTP_404_NOT_FOUND)

        vis, _ = DepartmentRuleVisibility.objects.get_or_create(department=dept, rule_key=rule)
        vis.is_visible = is_visible
        vis.save(update_fields=['is_visible'])

        # Refresh so serializer FK traversal hits the already-loaded instances
        vis.department = dept
        vis.rule_key = rule
        return Response(DepartmentRuleVisibilitySerializer(vis).data)


# ---------------------------------------------------------------------------
# Creditor visibility
# ---------------------------------------------------------------------------

class DepartmentCreditorsView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        creditors = CreditorCriteria.objects.filter(is_active=True).order_by('creditor_name')
        vis_map = {
            v.creditor_id: v.is_visible
            for v in DepartmentCreditorVisibility.objects.filter(department=dept)
        }
        result = [
            {
                'id': c.id,
                'name': c.creditor_name,
                'representative': c.representative,
                'parent_group': c.parent_group,
                'status': c.status,
                'min_dividend_pence': c.min_dividend_pence,
                'is_visible': vis_map.get(c.id, True),
            }
            for c in creditors
        ]
        return Response(result)


class DepartmentCreditorsToggleView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        creditor_id = request.data.get('creditor_id')
        is_visible = request.data.get('is_visible')

        if creditor_id is None:
            return Response({"detail": "creditor_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if is_visible is None:
            return Response({"detail": "is_visible is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            creditor = CreditorCriteria.objects.get(pk=creditor_id)
        except CreditorCriteria.DoesNotExist:
            return Response({"detail": "Creditor not found."}, status=status.HTTP_404_NOT_FOUND)

        vis, _ = DepartmentCreditorVisibility.objects.get_or_create(department=dept, creditor=creditor)
        vis.is_visible = is_visible
        vis.save(update_fields=['is_visible'])

        vis.department = dept
        vis.creditor = creditor
        return Response(DepartmentCreditorVisibilitySerializer(vis).data)


# ---------------------------------------------------------------------------
# Council visibility
# ---------------------------------------------------------------------------

class DepartmentCouncilsView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        councils = CouncilRule.objects.all().order_by('council_name')
        vis_map = {
            v.council_id: v.is_visible
            for v in DepartmentCouncilVisibility.objects.filter(department=dept)
        }
        result = [
            {
                'id': c.id,
                'name': c.council_name,
                'is_visible': vis_map.get(c.id, True),
            }
            for c in councils
        ]
        return Response(result)


class DepartmentCouncilsToggleView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        council_id = request.data.get('council_id')
        is_visible = request.data.get('is_visible')

        if council_id is None:
            return Response({"detail": "council_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if is_visible is None:
            return Response({"detail": "is_visible is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            council = CouncilRule.objects.get(pk=council_id)
        except CouncilRule.DoesNotExist:
            return Response({"detail": "Council not found."}, status=status.HTTP_404_NOT_FOUND)

        vis, _ = DepartmentCouncilVisibility.objects.get_or_create(department=dept, council=council)
        vis.is_visible = is_visible
        vis.save(update_fields=['is_visible'])

        vis.department = dept
        vis.council = council
        return Response(DepartmentCouncilVisibilitySerializer(vis).data)


# ---------------------------------------------------------------------------
# SFS (ExpenditureGuideline) visibility
# ---------------------------------------------------------------------------

def _guideline_vis_dict(g, is_visible):
    return {
        'id': g.id,
        'category': g.category,
        'label': g.label,
        'category_group': g.category_group.name if g.category_group else None,
        'adult_1': float(g.adult_1),
        'adult_2': float(g.adult_2),
        'is_visible': is_visible,
    }


class DepartmentSFSView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        guidelines = ExpenditureGuideline.objects.select_related('category_group').order_by(
            'category_group__sort_order', 'sort_order', 'category'
        )
        vis_map = {
            v.guideline_id: v.is_visible
            for v in DepartmentSFSVisibility.objects.filter(department=dept)
        }
        result = [_guideline_vis_dict(g, vis_map.get(g.id, True)) for g in guidelines]
        return Response(result)


class DepartmentSFSToggleView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        guideline_id = request.data.get('guideline_id')
        is_visible = request.data.get('is_visible')

        if guideline_id is None:
            return Response({"detail": "guideline_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if is_visible is None:
            return Response({"detail": "is_visible is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            guideline = ExpenditureGuideline.objects.select_related('category_group').get(pk=guideline_id)
        except ExpenditureGuideline.DoesNotExist:
            return Response({"detail": "Guideline not found."}, status=status.HTTP_404_NOT_FOUND)

        vis, _ = DepartmentSFSVisibility.objects.get_or_create(department=dept, guideline=guideline)
        vis.is_visible = is_visible
        vis.save(update_fields=['is_visible'])

        return Response(_guideline_vis_dict(guideline, vis.is_visible))


# ---------------------------------------------------------------------------
# Feature access
# ---------------------------------------------------------------------------

ALL_FEATURE_KEYS = [
    'general_creditors',
    'representative_creditors',
    'global_rules',
    'councils',
    'dividends',
    'sfs_guidelines',
    'run_assessment',
    'decisions',
    'evidence',
    'user_management',
]


class DepartmentFeaturesView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        access_map = {
            a.feature_key: a.is_enabled
            for a in DepartmentFeatureAccess.objects.filter(department=dept)
        }
        result = [
            {'feature_key': key, 'is_enabled': access_map.get(key, True)}
            for key in ALL_FEATURE_KEYS
        ]
        return Response(result)


class DepartmentFeaturesToggleView(APIView):
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        feature_key = request.data.get('feature_key')
        is_enabled = request.data.get('is_enabled')

        if not feature_key:
            return Response({"detail": "feature_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        if feature_key not in ALL_FEATURE_KEYS:
            return Response({"detail": f"Invalid feature_key '{feature_key}'."}, status=status.HTTP_400_BAD_REQUEST)
        if is_enabled is None:
            return Response({"detail": "is_enabled is required."}, status=status.HTTP_400_BAD_REQUEST)

        access, _ = DepartmentFeatureAccess.objects.get_or_create(
            department=dept, feature_key=feature_key
        )
        access.is_enabled = is_enabled
        access.save(update_fields=['is_enabled'])

        return Response({'feature_key': feature_key, 'is_enabled': access.is_enabled})


class MyPermissionsView(APIView):
    """Returns the current user's permission level (READ/WRITE) per feature."""
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.is_staff:
            return Response([{'feature_key': k, 'permission_level': 'WRITE'} for k in PERMISSION_FEATURES])

        dept = get_user_department(user)
        if dept is None:
            return Response([{'feature_key': k, 'permission_level': 'READ'} for k in PERMISSION_FEATURES])

        perm_map = {
            p.feature_key: p.permission_level
            for p in DepartmentFeaturePermission.objects.filter(department=dept)
        }
        return Response([
            {'feature_key': key, 'permission_level': perm_map.get(key, 'READ')}
            for key in PERMISSION_FEATURES
        ])


class MyFeaturesView(APIView):
    authentication_classes = _AUTH
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.is_staff:
            return Response([{'feature_key': k, 'is_enabled': True} for k in ALL_FEATURE_KEYS])

        dept = get_user_department(user)
        if dept is None:
            return Response([{'feature_key': k, 'is_enabled': True} for k in ALL_FEATURE_KEYS])

        access_records = list(DepartmentFeatureAccess.objects.filter(department=dept))
        access_map = {a.feature_key: a.is_enabled for a in access_records}
        return Response([
            {'feature_key': key, 'is_enabled': access_map.get(key, True)}
            for key in ALL_FEATURE_KEYS
        ])


# ---------------------------------------------------------------------------
# Feature permissions (READ/WRITE scope)
# ---------------------------------------------------------------------------

PERMISSION_FEATURES = [
    'general_creditors',
    'representative_creditors',
    'global_rules',
    'councils',
    'dividends',
    'sfs_guidelines',
]


class DepartmentPermissionsView(APIView):
    """Get all permission levels for a department."""
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def get(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        perm_map = {
            p.feature_key: p.permission_level
            for p in DepartmentFeaturePermission.objects.filter(department=dept)
        }
        result = [
            {
                'feature_key': key,
                'permission_level': perm_map.get(key, 'READ'),
            }
            for key in PERMISSION_FEATURES
        ]
        return Response(result)


class DepartmentPermissionSetView(APIView):
    """Set permission level for a specific feature."""
    authentication_classes = _AUTH
    permission_classes = _ADMIN

    def post(self, request, pk):
        try:
            dept = Department.objects.get(pk=pk)
        except Department.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        feature_key = request.data.get('feature_key')
        permission_level = request.data.get('permission_level')

        if not feature_key:
            return Response({"detail": "feature_key is required."}, status=status.HTTP_400_BAD_REQUEST)
        if feature_key not in PERMISSION_FEATURES:
            return Response(
                {"detail": f"Invalid feature_key '{feature_key}'. Must be one of: {', '.join(PERMISSION_FEATURES)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if permission_level not in ['READ', 'WRITE']:
            return Response(
                {"detail": "permission_level must be 'READ' or 'WRITE'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        perm, _ = DepartmentFeaturePermission.objects.get_or_create(
            department=dept,
            feature_key=feature_key,
        )
        perm.permission_level = permission_level
        perm.save(update_fields=['permission_level'])

        return Response({
            'feature_key': feature_key,
            'permission_level': perm.permission_level,
        })
