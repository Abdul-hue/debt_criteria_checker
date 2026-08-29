from django.contrib import admin
from .models import (
    CreditorCriteria, GlobalCriteria, Voter, Application, EvidenceLedger,
    CriteriaDecision, GuidelineCategory, ExpenditureGuideline, CreditReport,
    CouncilTaxEvidence,
    Department, UserProfile,
    DepartmentRuleVisibility, DepartmentCreditorVisibility, DepartmentCouncilVisibility,
    DepartmentSFSVisibility, DepartmentFeatureAccess, DepartmentFeaturePermission,
    CreditorVoteSummary,
)


@admin.register(CreditorCriteria)
class CreditorCriteriaAdmin(admin.ModelAdmin):
    list_display = [
        'creditor_name', 'representative', 'parent_group',
        'min_dividend_pence', 'account_age_months', 'fees_cap_percentage',
        'is_active', 'last_updated',
    ]
    list_filter = ['is_active', 'representative']
    search_fields = ['creditor_name', 'trading_names', 'parent_group']
    readonly_fields = ['last_updated']
    fieldsets = (
        ('Identity', {
            'fields': ('creditor_name', 'trading_names', 'parent_group', 'representative',
                       'source_sheet', 'is_active', 'last_updated'),
        }),
        ('Dividend', {
            'fields': ('min_dividend_pence', 'dividend_notes', 'conditional_voter_min_dividend_pence'),
        }),
        ('Age & Repayability', {
            'fields': ('account_age_months', 'reject_if_debt_repayable_within_months'),
        }),
        ('Asset & Vehicle', {
            'fields': ('reject_if_client_still_has_asset', 'vehicle_arrears_repossession_months',
                       'termination_risk_if_vehicle_on_finance'),
        }),
        ('Financial Position', {
            'fields': ('reject_if_equity_exceeds_debt', 'reject_if_majority_share_exceeds_pct',
                       'fees_cap_percentage', 'min_di_for_fees_pence'),
        }),
        ('Application Checks', {
            'fields': ('reject_if_ie_doesnt_match_application', 'requires_pg_called_up',
                       'requires_arrangement_call_before_proposing',
                       'requires_grant_overpayment_only'),
        }),
        ('Hard Blocks', {
            'fields': ('blocked_until_cleared', 'reject_if_never_made_payment',
                       'reject_if_second_iva', 'reject_if_ccj', 'reject_if_aoe',
                       'reject_if_in_dmp', 'reject_if_police_employed', 'fraud_claim_risk'),
        }),
        ('Notes', {
            'fields': ('criteria_notes',),
            'classes': ('collapse',),
        }),
    )


@admin.register(GlobalCriteria)
class GlobalCriteriaAdmin(admin.ModelAdmin):
    list_display = ['rule_key', 'rule_name', 'criteria_set', 'severity', 'is_active', 'last_updated']
    list_filter = ['criteria_set', 'severity']
    search_fields = ['rule_key', 'rule_name']
    readonly_fields = ['last_updated']


@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['aryza_reference', 'client_name', 'created_at']
    search_fields = ['aryza_reference', 'client_name']


@admin.register(EvidenceLedger)
class EvidenceLedgerAdmin(admin.ModelAdmin):
    list_display = ['application', 'entry_type', 'created_at']
    list_filter = ['entry_type', 'created_at']
    search_fields = ['application__client_name']


@admin.register(CriteriaDecision)
class CriteriaDecisionAdmin(admin.ModelAdmin):
    list_display = ['application_id', 'client_name', 'recommended_solution', 'passes_all_hard_blocks', 'source', 'triggered_at']
    list_filter = ['recommended_solution', 'source', 'passes_all_hard_blocks', 'triggered_at']
    search_fields = ['application_id', 'client_name']
    readonly_fields = ['id', 'triggered_at', 'input_snapshot', 'decision_output']


@admin.register(GuidelineCategory)
class GuidelineCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order', 'upper_cap']
    ordering = ['sort_order']


@admin.register(ExpenditureGuideline)
class ExpenditureGuidelineAdmin(admin.ModelAdmin):
    list_display = ['label', 'category', 'category_group', 'min', 'max', 'sort_order', 'updated_at']
    list_filter = ['category_group', 'min', 'max']
    search_fields = ['label', 'category']
    ordering = ['category_group__sort_order', 'sort_order', 'category']


@admin.register(CreditReport)
class CreditReportAdmin(admin.ModelAdmin):
    list_display = ['aryza_reference', 'agency', 'extraction_status', 'accounts_found_display', 'uploaded_by', 'created_at']
    list_filter = ['extraction_status', 'agency']
    search_fields = ['aryza_reference', 'client_name_on_report']
    readonly_fields = ['extracted_data', 'extraction_error', 'created_at', 'updated_at']

    def accounts_found_display(self, obj):
        if obj.extracted_data and "accounts" in obj.extracted_data:
            return len(obj.extracted_data["accounts"])
        return 0
    accounts_found_display.short_description = "Accounts Found"


@admin.register(CouncilTaxEvidence)
class CouncilTaxEvidenceAdmin(admin.ModelAdmin):
    list_display = [
        'aryza_reference', 'extraction_status', 'account_reference',
        'balance_pence', 'council_name', 'liability_order_date',
        'uploaded_by', 'created_at',
    ]
    list_filter = ['extraction_status', 'council_name']
    search_fields = ['aryza_reference', 'account_reference', 'council_name', 'client_salutation_name']
    readonly_fields = ['raw_text', 'extraction_error', 'created_at', 'updated_at']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department']
    list_filter = ['department']
    search_fields = ['user__username', 'user__email']
    raw_id_fields = ['user']


@admin.register(DepartmentRuleVisibility)
class DepartmentRuleVisibilityAdmin(admin.ModelAdmin):
    list_display = ['department', 'rule_key', 'is_visible']
    list_filter = ['department', 'is_visible']
    search_fields = ['rule_key__rule_key', 'rule_key__rule_name']


@admin.register(DepartmentCreditorVisibility)
class DepartmentCreditorVisibilityAdmin(admin.ModelAdmin):
    list_display = ['department', 'creditor', 'is_visible']
    list_filter = ['department', 'is_visible']
    search_fields = ['creditor__creditor_name']


@admin.register(DepartmentCouncilVisibility)
class DepartmentCouncilVisibilityAdmin(admin.ModelAdmin):
    list_display = ['department', 'council', 'is_visible']
    list_filter = ['department', 'is_visible']
    search_fields = ['council__council_name']


@admin.register(DepartmentSFSVisibility)
class DepartmentSFSVisibilityAdmin(admin.ModelAdmin):
    list_display = ['department', 'guideline', 'is_visible']
    list_filter = ['department', 'is_visible']
    search_fields = ['guideline__label', 'guideline__category']


@admin.register(DepartmentFeatureAccess)
class DepartmentFeatureAccessAdmin(admin.ModelAdmin):
    list_display = ['department', 'feature_key', 'is_enabled']
    list_filter = ['department', 'feature_key', 'is_enabled']
    search_fields = ['department__name', 'feature_key']


@admin.register(DepartmentFeaturePermission)
class DepartmentFeaturePermissionAdmin(admin.ModelAdmin):
    list_display = ['department', 'feature_key', 'permission_level', 'updated_at']
    list_filter = ['department', 'feature_key', 'permission_level']
    search_fields = ['department__name', 'feature_key']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Department & Feature', {
            'fields': ('department', 'feature_key'),
            'description': 'Select which department and feature to configure permissions for.'
        }),
        ('Permission Level', {
            'fields': ('permission_level',),
            'description': 'READ: View-only access. WRITE: Full access including edit, delete, and add operations.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(CreditorVoteSummary)
class CreditorVoteSummaryAdmin(admin.ModelAdmin):
    list_display = [
        'creditor_criteria', 'council_rule', 'county_council',
        'total_votes', 'accepted_count', 'rejected_count',
        'latest_vote_date', 'latest_vote_outcome',
        'crm_rows_covered', 'last_synced_at'
    ]
    list_filter = ['latest_vote_outcome', 'last_synced_at']
    search_fields = [
        'creditor_criteria__creditor_name',
        'council_rule__council_name',
        'county_council__county_name'
    ]
    readonly_fields = ['last_synced_at']