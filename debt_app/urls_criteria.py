from django.urls import path
from debt_app.views.criteria_views import (
    AssessCaseView,
    AssessHistoryView,
    AssessHistoryDetailView,
    CreditorListView,
    CreditorDetailView,
    RulesListView,
    RulesDetailView,
    RuleHistoryView,
    CouncilRuleListView,
    CouncilRuleDetailView,
    CountyCouncilListView,
    CountyCouncilDetailView,
    ApplicationListView,
    ApplicationDetailView,
    EvidenceLedgerListView,
    EvidenceLedgerDetailView,
    VoterListView,
    VoterDetailView,
    UserListView,
    UserDetailView,
    ExpenditureGuidelineCategoryListView,
    ExpenditureGuidelineCategoryDetailView,
    ExpenditureGuidelineListView,
    ExpenditureGuidelineDetailView,
    CreditReportUploadView,
    CouncilTaxEvidenceUploadView,
    MyDepartmentView,
    CreditorOutcomeListView,
    CreditorAuditLogView,
    CreditorVoteSummaryView,
    CrmSyncTriggerView,
    CrmSyncStatusView,
    CrmSyncHistoryView,
    CrmSyncRunCreditorBreakdownView,
    CrmSyncTodayView,
)
from debt_app.views.evaluate_view import EvaluateCaseView
from debt_app.views.evaluation_history_view import EvaluationHistoryView
from debt_app.views.internal_sfs_views import (
    InternalGuidelineListView,
    InternalGuidelineDetailView,
    InternalGuidelineByCategoryView,
    InternalGuidelineCategoryListView,
    InternalGuidelineCategoryDetailView,
)
from debt_app.views.dept_views import (
    DepartmentListView,
    DepartmentDetailView,
    UserDepartmentView,
    DepartmentRulesView,
    DepartmentRulesToggleView,
    DepartmentCreditorsView,
    DepartmentCreditorsToggleView,
    DepartmentCouncilsView,
    DepartmentCouncilsToggleView,
    DepartmentSFSView,
    DepartmentSFSToggleView,
    DepartmentFeaturesView,
    DepartmentFeaturesToggleView,
    DepartmentPermissionsView,
    DepartmentPermissionSetView,
    MyFeaturesView,
    MyPermissionsView,
)

urlpatterns = [
    path("assess/",                         AssessCaseView.as_view()),
    path('cases/<str:case_id>/evaluate', EvaluateCaseView.as_view(), name='evaluate-case'),
    path('cases/<str:case_id>/evaluations', EvaluationHistoryView.as_view(), name='evaluation-history'),
    path("assess/history/",                 AssessHistoryView.as_view()),
    path("assess/history/<uuid:id>/",       AssessHistoryDetailView.as_view()),
    path("creditors/",                      CreditorListView.as_view()),
    path("creditors/<int:id>/",             CreditorDetailView.as_view()),
    path('creditors/<int:id>/outcomes/',        CreditorOutcomeListView.as_view(),   name='creditor-outcomes'),
    path('creditors/<int:id>/audit-log/',       CreditorAuditLogView.as_view(),      name='creditor-audit-log'),
    path('creditors/<int:id>/vote-summary/', CreditorVoteSummaryView.as_view(), {'type': 'creditors'}, name='creditor-vote-summary'),
    path('councils/<int:id>/vote-summary/', CreditorVoteSummaryView.as_view(), {'type': 'councils'}, name='council-vote-summary'),
    path('county-councils/<int:id>/vote-summary/', CreditorVoteSummaryView.as_view(), {'type': 'county-councils'}, name='county-council-vote-summary'),
    path('crm-sync/trigger/', CrmSyncTriggerView.as_view(), name='crm-sync-trigger'),
    path('crm-sync/status/<int:pk>/', CrmSyncStatusView.as_view(), name='crm-sync-status'),
    path('crm-sync/history/', CrmSyncHistoryView.as_view(), name='crm-sync-history'),
    path('crm-sync/creditors/<int:run_id>/', CrmSyncRunCreditorBreakdownView.as_view(), name='crm-sync-run-creditors'),
    path('crm-sync/today/', CrmSyncTodayView.as_view(), name='crm-sync-today'),
    path("rules/",                          RulesListView.as_view()),
    path("rules/<str:rule_key>/",           RulesDetailView.as_view()),
    path("rules/<str:rule_key>/history/", RuleHistoryView.as_view()),
    path("councils/",                       CouncilRuleListView.as_view()),
    path("councils/<int:pk>/",              CouncilRuleDetailView.as_view()),
    path("county-councils/",                CountyCouncilListView.as_view()),
    path("county-councils/<int:pk>/",       CountyCouncilDetailView.as_view()),
    path("applications/",                   ApplicationListView.as_view()),
    path("applications/<int:pk>/",          ApplicationDetailView.as_view()),
    path("evidence/",                       EvidenceLedgerListView.as_view()),
    path("evidence/<int:pk>/",              EvidenceLedgerDetailView.as_view()),
    path("voters/",                         VoterListView.as_view()),
    path("voters/<int:pk>/",               VoterDetailView.as_view()),
    path("users/",                          UserListView.as_view()),
    path("users/<int:pk>/",                UserDetailView.as_view()),
    path("sfs/categories/",                ExpenditureGuidelineCategoryListView.as_view()),
    path("sfs/categories/<int:pk>/",       ExpenditureGuidelineCategoryDetailView.as_view()),
    path("sfs/guidelines/",               ExpenditureGuidelineListView.as_view()),
    path("sfs/guidelines/<int:pk>/",      ExpenditureGuidelineDetailView.as_view()),

    # --- SFS guidelines, service-to-service (no JWT; CA backend on this server) ---
    # by-category/ is declared before <int:key> only for readability — the int
    # converter can never swallow the literal prefix.
    path("internal/sfs/guidelines/",                     InternalGuidelineListView.as_view(),           name="internal-sfs-guideline-list"),
    path("internal/sfs/guidelines/by-category/<str:key>/", InternalGuidelineByCategoryView.as_view(),   name="internal-sfs-guideline-by-category"),
    path("internal/sfs/guidelines/<int:key>/",           InternalGuidelineDetailView.as_view(),         name="internal-sfs-guideline-detail"),
    path("internal/sfs/categories/",                     InternalGuidelineCategoryListView.as_view(),   name="internal-sfs-category-list"),
    path("internal/sfs/categories/<int:pk>/",            InternalGuidelineCategoryDetailView.as_view(), name="internal-sfs-category-detail"),
    path("upload-credit-report/",         CreditReportUploadView.as_view(), name="upload-credit-report"),
    path("council-tax-evidence/upload/",  CouncilTaxEvidenceUploadView.as_view(), name="council-tax-evidence-upload"),
    path("my-department/",               MyDepartmentView.as_view(), name="my-department"),

    # --- Department CRUD (admin only) ---
    path("departments/",                              DepartmentListView.as_view(),             name="department-list"),
    path("departments/<int:pk>/",                     DepartmentDetailView.as_view(),           name="department-detail"),

    # --- User → Department assignment (admin only) ---
    path("users/<int:pk>/department/",                UserDepartmentView.as_view(),             name="user-department"),

    # --- Rule visibility (admin only) ---
    path("departments/<int:pk>/rules/",               DepartmentRulesView.as_view(),            name="department-rules"),
    path("departments/<int:pk>/rules/toggle/",        DepartmentRulesToggleView.as_view(),      name="department-rules-toggle"),

    # --- Creditor visibility (admin only) ---
    path("departments/<int:pk>/creditors/",           DepartmentCreditorsView.as_view(),        name="department-creditors"),
    path("departments/<int:pk>/creditors/toggle/",    DepartmentCreditorsToggleView.as_view(),  name="department-creditors-toggle"),

    # --- Council visibility (admin only) ---
    path("departments/<int:pk>/councils/",            DepartmentCouncilsView.as_view(),         name="department-councils"),
    path("departments/<int:pk>/councils/toggle/",     DepartmentCouncilsToggleView.as_view(),   name="department-councils-toggle"),

    # --- SFS guideline visibility (admin only) ---
    path("departments/<int:pk>/sfs/",                 DepartmentSFSView.as_view(),              name="department-sfs"),
    path("departments/<int:pk>/sfs/toggle/",          DepartmentSFSToggleView.as_view(),        name="department-sfs-toggle"),

    # --- Feature access (admin only, except my-features) ---
    path("departments/<int:pk>/features/",            DepartmentFeaturesView.as_view(),         name="department-features"),
    path("departments/<int:pk>/features/toggle/",     DepartmentFeaturesToggleView.as_view(),   name="department-features-toggle"),
    path("my-features/",                              MyFeaturesView.as_view(),                 name="my-features"),
    path("my-permissions/",                           MyPermissionsView.as_view(),              name="my-permissions"),

    # --- Feature permissions (admin only) ---
    path("departments/<int:pk>/permissions/",         DepartmentPermissionsView.as_view(),      name="department-permissions"),
    path("departments/<int:pk>/permissions/set/",     DepartmentPermissionSetView.as_view(),    name="department-permission-set"),
]
