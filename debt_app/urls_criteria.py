from django.urls import path
from debt_app.views.criteria_views import (
    AssessCaseView,
    AssessHistoryView,
    AssessHistoryDetailView,
    CreditorListView,
    CreditorDetailView,
    RulesListView,
    RulesDetailView,
)

urlpatterns = [
    path("assess/",                    AssessCaseView.as_view()),
    path("assess/history/",            AssessHistoryView.as_view()),
    path("assess/history/<uuid:id>/",  AssessHistoryDetailView.as_view()),
    path("creditors/",                 CreditorListView.as_view()),
    path("creditors/<int:id>/",        CreditorDetailView.as_view()),
    path("rules/",                     RulesListView.as_view()),
    path("rules/<str:rule_key>/",      RulesDetailView.as_view()),
]