from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from debt_app.views.auth_views import email_token_obtain_pair
from django.views.decorators.csrf import csrf_exempt
from debt_app.views.assess_view import DirectAssessView
from debt_app.views.simple import AssessView

print("\n--- LOADING FLAT CORE URLS.PY ---")


from django.http import HttpResponse


def ping(request):
    return HttpResponse("OK")


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/ping/', ping),

    path('api/assess/', AssessView.as_view(), name='assess'),

    # Task 6B — direct case assessment (no auth, accepts raw case JSON)
    path('api/v1/assess/', csrf_exempt(DirectAssessView.as_view())),

    # Authentication endpoints
    path('api/token/', email_token_obtain_pair, name='email_token_obtain_pair'),
    path('api/token/username/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # All criteria endpoints (assess, creditors, rules, councils, applications, evidence, voters, users)
    path('api/v1/criteria/', include('debt_app.urls_criteria')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
