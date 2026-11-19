"""
A creditor whose minimum dividend is not met votes NO.

Case 434115 (2026-11-20): Castle Community Bank needs 30p in the pound, the
case offers 11p. DIVIDEND-BELOW-MIN said "this creditor is expected to reject
the IVA", yet its £13,986 sat in Accepted debt and Rejected debt was £0.00 --
the per-creditor DIVIDEND-CHECK-FAIL was a finding only and never moved the
vote. EXCEL_CRITERIA_REFERENCE.md, Dividends: "If the estimated IVA dividend
is below this, the creditor will reject."
"""
from decimal import Decimal

from django.test import TestCase

from debt_app.engine.criteria import assess_case
from debt_app.models import CreditorCriteria


class DividendBelowMinVoteTests(TestCase):
    #: Made-up names so seeded criteria rows cannot interfere.
    NEEDS_30P = "Dividend Test Community Bank"
    NO_MINIMUM = "Dividend Test Lender"

    def setUp(self):
        CreditorCriteria.objects.update_or_create(
            creditor_name=self.NEEDS_30P,
            defaults=dict(representative="NONE", status="ACCEPT", is_active=True,
                          min_dividend_pence=30),
        )
        CreditorCriteria.objects.update_or_create(
            creditor_name=self.NO_MINIMUM,
            defaults=dict(representative="NONE", status="ACCEPT", is_active=True,
                          min_dividend_pence=None),
        )

    def _assess(self, monthly_di):
        return assess_case({
            "application_id": "DIV-VOTE",
            "assessment_date": "2026-11-20",
            "monthly_di": monthly_di,
            "creditors": [
                {"name": self.NEEDS_30P, "balance": 14000.0, "creditor_type": "personal_loan"},
                {"name": self.NO_MINIMUM, "balance": 6000.0, "creditor_type": "personal_loan"},
            ],
        }, set())

    def _position(self, result, name):
        return next(p for p in result["creditor_positions"]
                    if p.get("creditor_name") == name)

    def test_low_dividend_turns_the_creditor_into_a_no_vote(self):
        result = self._assess(monthly_di=50.0)
        self.assertLess(result["dividend_analysis"]["estimated_pence"], 30)

        castle = self._position(result, self.NEEDS_30P)
        self.assertEqual(castle["effective_status"], "REJECT")
        self.assertIn("DIVIDEND-CHECK-FAIL", {f["code"] for f in castle["findings"]})
        self.assertTrue([r for r in result["flags"]
                         if r.rule_id == "DIVIDEND-BELOW-MIN" and self.NEEDS_30P in r.message])

        # Only the lender with no minimum supports the IVA.
        majority = result["majority_analysis"]
        self.assertEqual(Decimal(str(majority["voting_debt"])), Decimal("6000"))
        self.assertFalse(majority["achievable"])

    def test_dividend_that_meets_the_minimum_keeps_the_yes_vote(self):
        result = self._assess(monthly_di=500.0)
        self.assertGreaterEqual(result["dividend_analysis"]["estimated_pence"], 30)

        castle = self._position(result, self.NEEDS_30P)
        self.assertEqual(castle["effective_status"], "ACCEPT")
        self.assertEqual(Decimal(str(result["majority_analysis"]["voting_debt"])), Decimal("20000"))
