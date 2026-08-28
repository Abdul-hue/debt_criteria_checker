"""
Tests for _council_to_dict serializer completeness.

Verifies that the three joint-case reject_if_* fields present on CouncilRule
and evaluated by the engine are returned by the API serializer.
"""

from django.test import TestCase

from debt_app.models import CouncilRule
from debt_app.views.criteria_views import _council_to_dict


class CouncilToDictJointFieldsTest(TestCase):
    def setUp(self):
        self.council = CouncilRule.objects.create(
            council_name="Test Joint Council",
            status="ACCEPT",
            reject_if_joint_one_party_only=True,
            reject_if_joint_both_parties=True,
            reject_if_joint_one_employed=True,
        )

    def test_reject_if_joint_one_party_only_present(self):
        d = _council_to_dict(self.council)
        self.assertIn("reject_if_joint_one_party_only", d)
        self.assertTrue(d["reject_if_joint_one_party_only"])

    def test_reject_if_joint_both_parties_present(self):
        d = _council_to_dict(self.council)
        self.assertIn("reject_if_joint_both_parties", d)
        self.assertTrue(d["reject_if_joint_both_parties"])

    def test_reject_if_joint_one_employed_present(self):
        d = _council_to_dict(self.council)
        self.assertIn("reject_if_joint_one_employed", d)
        self.assertTrue(d["reject_if_joint_one_employed"])
