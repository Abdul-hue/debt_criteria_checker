"""
Auth enforcement tests for AssessView (/api/assess/) and DirectAssessView (/api/v1/assess/).

Before this fix both endpoints were plain Django Views with no auth — an unauthenticated
POST returned 200.  After the fix they are DRF APIViews with JWTAuthentication +
IsAuthenticated, so unauthenticated requests return 401.

Pre-fix evidence: simple.py declared `class AssessView(View)` with the docstring
"POST /api/assess/ — internal-only, no auth." and assess_view.py declared
`class DirectAssessView(View)` with the comment "no auth, accepts raw case JSON".
Neither class had authentication_classes or permission_classes set.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

MINIMAL_PAYLOAD = {
    "client_name": "Auth Test Client",
    "disposable_income": 300,
    "total_income": 2000,
    "creditors": [
        {"creditor_name": "Test Bank", "balance": 5000, "debt_type": "credit_card"},
    ],
}

EXPECTED_TOP_LEVEL_KEYS = {"overall", "hard_blocks", "flags", "info", "passed"}


class AssessViewAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser_assess", password="pass")

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/api/assess/",
            data=json.dumps(MINIMAL_PAYLOAD),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401, f"Expected 401, got {resp.status_code}")

    def test_authenticated_returns_200_with_expected_shape(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/assess/",
            data=json.dumps(MINIMAL_PAYLOAD),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.content}")
        body = json.loads(resp.content)
        for key in EXPECTED_TOP_LEVEL_KEYS:
            self.assertIn(key, body, f"Response missing key '{key}'")

    def test_authenticated_bad_json_returns_400(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/assess/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class DirectAssessViewAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser_direct", password="pass")

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/api/v1/assess/",
            data=json.dumps(MINIMAL_PAYLOAD),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401, f"Expected 401, got {resp.status_code}")

    def test_authenticated_returns_200_with_expected_shape(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/v1/assess/",
            data=json.dumps(MINIMAL_PAYLOAD),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.content}")
        body = json.loads(resp.content)
        for key in EXPECTED_TOP_LEVEL_KEYS:
            self.assertIn(key, body, f"Response missing key '{key}'")
        # DirectAssessView returns richer shape — confirm additional keys
        for key in ("overall_status", "summary", "creditor_positions", "majority_analysis"):
            self.assertIn(key, body, f"DirectAssessView response missing key '{key}'")

    def test_authenticated_bad_json_returns_400(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/v1/assess/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
