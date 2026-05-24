from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from debt_app.models import CriteriaDecision
import uuid

class EvaluationHistoryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.case_id = "ARY-2026-TEST"
        
        # Get JWT token for authenticated requests
        refresh = RefreshToken.for_user(self.user)
        self.auth_header = f'Bearer {refresh.access_token}'

    def _create_decision(self, case_id, user, index):
        return CriteriaDecision.objects.create(
            application_id=case_id,
            client_name=f"Client {index}",
            input_snapshot={"test": "data"},
            decision_output={"result": "passed"},
            result_json={
                "decision": "ELIGIBLE",
                "recommended_solution": {"code": "IVA", "label": "IVA", "confidence": "HIGH"},
                "requires_review": False,
                "flagged_criteria": []
            },
            recommended_solution="IVA",
            passes_all_hard_blocks=True,
            triggered_by=user,
            source="CASE_ASSESSMENT"
        )

    def test_get_history_authenticated(self):
        # Create 3 decisions
        for i in range(3):
            self._create_decision(self.case_id, self.user, i)
        
        url = reverse('evaluation-history', kwargs={'case_id': self.case_id})
        response = self.client.get(url, HTTP_AUTHORIZATION=self.auth_header)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
        self.assertEqual(response.data['count'], 3)
        
        # Check shape of first item
        item = response.data['results'][0]
        self.assertIn('evaluation_id', item)
        self.assertEqual(item['decision'], 'ELIGIBLE')
        self.assertEqual(item['evaluated_by'], 'testuser')
        self.assertEqual(item['recommended_solution']['code'], 'IVA')
        self.assertEqual(item['flagged_criteria_count'], 0)

    def test_get_history_empty(self):
        url = reverse('evaluation-history', kwargs={'case_id': 'NON-EXISTENT'})
        response = self.client.get(url, HTTP_AUTHORIZATION=self.auth_header)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
        self.assertEqual(response.data['count'], 0)

    def test_get_history_unauthenticated(self):
        url = reverse('evaluation-history', kwargs={'case_id': self.case_id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pagination(self):
        # Create 15 decisions
        for i in range(15):
            self._create_decision(self.case_id, self.user, i)
            
        url = reverse('evaluation-history', kwargs={'case_id': self.case_id})
        
        # Page 1
        response = self.client.get(url, {'page': 1}, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(len(response.data['results']), 10)
        self.assertTrue(response.data['has_next'])
        
        # Page 2
        response = self.client.get(url, {'page': 2}, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(len(response.data['results']), 5)
        self.assertFalse(response.data['has_next'])
