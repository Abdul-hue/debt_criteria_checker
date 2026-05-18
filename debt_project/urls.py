from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from debt_app.views.criteria_views import (
    AssessCaseView,
    AssessHistoryView,
    AssessHistoryDetailView,
    CreditorListView,
    CreditorDetailView,
    RulesListView,
    RulesDetailView,
)
from django.views.decorators.csrf import csrf_exempt
from debt_app.views.assess_view import DirectAssessView
from debt_app.views.simple import AssessView

print("\n--- LOADING FLAT CORE URLS.PY ---")


from django.http import HttpResponse


def ping(request):
    return HttpResponse("OK")


urlpatterns = [
    path('api/ping/', ping),

    path('api/assess/', AssessView.as_view(), name='assess'),

    # Task 6B — direct case assessment (no auth, accepts raw case JSON)
    path('api/v1/assess/', csrf_exempt(DirectAssessView.as_view())),

    # Aryza-backed assessment (JWT auth required)
    path('api/v1/criteria/assess/', AssessCaseView.as_view()),

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/criteria/assess/history/',            AssessHistoryView.as_view()),
    path('api/v1/criteria/assess/history/<uuid:id>/',  AssessHistoryDetailView.as_view()),
    path('api/v1/criteria/creditors/',                 CreditorListView.as_view()),
    path('api/v1/criteria/creditors/<int:id>/',        CreditorDetailView.as_view()),
    path('api/v1/criteria/rules/',                     RulesListView.as_view()),
    path('api/v1/criteria/rules/<str:rule_key>/',      RulesDetailView.as_view()),
]
