"""Department membership and department-scoped queryset filtering."""

from debt_app.models import Department, UserProfile

def get_user_department(user):
    """
    Returns the Department linked to the user via UserProfile.
    Falls back to the 'Default' department, or None if that doesn't exist.
    """
    try:
        profile = user.profile
        if profile.department_id:
            return profile.department
    except (UserProfile.DoesNotExist, AttributeError):
        # AttributeError covers AnonymousUser/None, which have no `.profile`.
        pass
    try:
        return Department.objects.get(name='Default')
    except Department.DoesNotExist:
        return None


def filter_by_department(queryset, model, user, visibility_model, fk_field):
    """
    Filter a queryset by department visibility.

    Admin users (is_staff=True) always receive the unfiltered queryset.
    Assessor users see everything EXCEPT records their department has explicitly
    marked is_visible=False (deny-list semantics). If no visibility entries exist
    the full queryset is returned — items are visible by default.

    Parameters
    ----------
    queryset         : base queryset to filter
    model            : the model class of the queryset (unused, kept for signature clarity)
    user             : the request user
    visibility_model : DepartmentRuleVisibility / DepartmentCreditorVisibility / DepartmentCouncilVisibility
    fk_field         : name of the FK field on visibility_model that points to the main model
                       (e.g. 'rule_key', 'creditor', 'council')
    """
    if user.is_staff:
        return queryset

    dept = get_user_department(user)
    if dept is None:
        return queryset

    dept_qs = visibility_model.objects.filter(department=dept)
    if not dept_qs.exists():
        return queryset

    # Determine which field on the target model to filter against.
    # FK with to_field='rule_key' → remote_field.field_name == 'rule_key'
    # FK to default PK          → remote_field.field_name == 'id'
    fk_meta = visibility_model._meta.get_field(fk_field)
    target_field = fk_meta.remote_field.field_name or 'pk'

    hidden_values = list(
        dept_qs.filter(is_visible=False)
        .values_list(fk_field + '_id', flat=True)
    )

    if not hidden_values:
        return queryset

    return queryset.exclude(**{target_field + '__in': hidden_values})
