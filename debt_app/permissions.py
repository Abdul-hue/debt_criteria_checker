from rest_framework.permissions import BasePermission

from debt_app.helpers import get_user_department
from debt_app.models import DepartmentFeatureAccess, DepartmentFeaturePermission


class HasFeatureAccess(BasePermission):
    """
    Checks that the requesting user's department has the feature enabled.

    Usage: set `required_feature = 'run_assessment'` on the view class.
    Admin users (is_staff=True) always pass. If no DepartmentFeatureAccess
    record exists for the department+feature combo the default is allowed.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        feature_key = getattr(view, 'required_feature', None)
        if not feature_key:
            return True
        dept = get_user_department(request.user)
        if not dept:
            return True
        has_any = DepartmentFeatureAccess.objects.filter(department=dept).exists()
        if not has_any:
            # No records seeded for this department — safe fallback
            return True
        access = DepartmentFeatureAccess.objects.filter(
            department=dept, feature_key=feature_key
        ).first()
        if access is None:
            # Records exist but this feature not explicitly enabled → deny
            return False
        return access.is_enabled


class HasWritePermission(BasePermission):
    """
    Checks that the requesting user's department has WRITE permission for the feature.

    Usage: set `required_feature = 'general_creditors'` on the view class for PUT/POST/DELETE.
    Admin users (is_staff=True) always pass.
    If no DepartmentFeaturePermission record exists, defaults to READ-only.
    
    Supported features: general_creditors, representative_creditors, global_rules,
                       councils, dividends, sfs_guidelines
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin users always have write permission
        if request.user.is_staff:
            return True
        
        # GET requests don't require write permission
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        feature_key = getattr(view, 'required_feature', None)
        if not feature_key:
            # No feature specified — deny write by default
            return False
        
        dept = get_user_department(request.user)
        if not dept:
            return False
        
        # Check if permission record exists for this department+feature
        perm = DepartmentFeaturePermission.objects.filter(
            department=dept,
            feature_key=feature_key
        ).first()
        
        if perm is None:
            # No permission record — default to READ-only (deny write)
            return False
        
        # Check if the permission level is WRITE
        return perm.permission_level == 'WRITE'


class HasReadPermission(BasePermission):
    """
    Checks that the requesting user's department has READ or WRITE permission for the feature.

    Usage: set `required_feature = 'general_creditors'` on the view class for GET.
    Admin users (is_staff=True) always pass.
    If no DepartmentFeaturePermission record exists, defaults to allowing read access.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin users always have read permission
        if request.user.is_staff:
            return True
        
        feature_key = getattr(view, 'required_feature', None)
        if not feature_key:
            # No feature specified — allow read by default
            return True
        
        dept = get_user_department(request.user)
        if not dept:
            return True
        
        # Check if permission record exists for this department+feature
        perm = DepartmentFeaturePermission.objects.filter(
            department=dept,
            feature_key=feature_key
        ).first()
        
        if perm is None:
            # No permission record — default to allowing read access
            return True
        
        # Both READ and WRITE allow read access
        return perm.permission_level in ['READ', 'WRITE']


class HasEnabledFeature(BasePermission):
    """
    Strict variant of HasFeatureAccess for the Lead Gen and criteria-change
    features: the user's department must have an explicit
    DepartmentFeatureAccess row with is_enabled=True for `required_feature`.

    Unlike HasFeatureAccess there is NO permissive fallback (no department,
    or a department with no feature records, is denied) — these features
    grant access to case data / live-criteria changes and must be opted into.
    Admin users (is_staff=True) always pass, matching the existing classes.

    `required_feature` may also be a dict keyed by HTTP method (e.g.
    {"GET": "lead_gen_reporting", "POST": "criteria_changes"}).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        feature_key = getattr(view, 'required_feature', None)
        if isinstance(feature_key, dict):
            feature_key = feature_key.get(request.method)
        if not feature_key:
            return False
        dept = get_user_department(request.user)
        if not dept:
            return False
        return DepartmentFeatureAccess.objects.filter(
            department=dept, feature_key=feature_key, is_enabled=True,
        ).exists()


def user_has_enabled_feature(user, feature_key):
    """Function form of HasEnabledFeature, for checks inside a view."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    dept = get_user_department(user)
    if not dept:
        return False
    return DepartmentFeatureAccess.objects.filter(
        department=dept, feature_key=feature_key, is_enabled=True,
    ).exists()


class DirectCriteriaEditAllowed(BasePermission):
    """
    Guard on the existing direct-edit endpoints for the managed criteria
    tables (creditors, rules, councils, county councils).

    Inert by default. When settings.CRITERIA_CHANGE_CONTROL_ENFORCED is True,
    direct create/update/delete is refused so live criteria can only change
    through the controlled Draft -> Trial -> Sign-off workflow
    (/api/v1/criteria/criteria-changes/). Reads are never affected.
    """

    message = (
        "Direct edits to live criteria are disabled. Propose the change through "
        "Criteria Changes so it can be trialled and signed off by a second manager."
    )

    def has_permission(self, request, view):
        from django.conf import settings
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return not getattr(settings, 'CRITERIA_CHANGE_CONTROL_ENFORCED', False)
