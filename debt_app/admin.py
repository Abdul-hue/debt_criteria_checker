from django.contrib import admin
from .models import CreditorCriteria, GlobalCriteria, Voter, Application, EvidenceLedger, CriteriaDecision


@admin.register(CreditorCriteria)
class CreditorCriteriaAdmin(admin.ModelAdmin):
    list_display = ['creditor_name', 'representative', 'parent_group', 'is_active', 'last_updated']
    list_filter = ['is_active', 'representative']
    search_fields = ['creditor_name', 'trading_names', 'parent_group']
    readonly_fields = ['last_updated']


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
