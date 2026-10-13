"""
Age-tiered minimum dividend (young_account_months / young_account_min_dividend_pence),
added for Loans by Mal: "if under 6 months but older than 3 months - has to 40p/£".
"""

from django.test import TestCase

from debt_app.engine.criteria import _check_creditor_individual, _parse_case
from debt_app.models import CreditorCriteria


def _codes(pos):
    return {f["code"] for f in pos["findings"]}


def _reason(pos, code):
    return next(f["reason"] for f in pos["findings"] if f["code"] == code)


class YoungAccountDividendTests(TestCase):
    def setUp(self):
        CreditorCriteria.objects.create(
            creditor_name="Loans by Mal", representative="NONE", status="WILL_CONSIDER", is_active=True,
            account_age_months=3, young_account_months=6, young_account_min_dividend_pence=40,
        )

    def _position(self, age, dividend):
        creditor = {"creditor_name": "Loans by Mal", "balance": 1200}
        if age is not None:
            creditor["account_age_months"] = age
        case = _parse_case({"creditors": [creditor]})
        case.update({"aryza_reference": "T", "client_name": "T"})
        return _check_creditor_individual(case, estimated_dividend_pence=dividend)[0]

    def test_young_account_raises_the_minimum(self):
        pos = self._position(age=4, dividend=30)
        self.assertIn("DIVIDEND-CHECK-FAIL", _codes(pos))
        self.assertIn("30p/£ < 40p/£ (account is 4 month(s) old, under 6 months)", _reason(pos, "DIVIDEND-CHECK-FAIL"))
        self.assertNotIn("CREDITOR-LOAN-TOO-RECENT-REJECT", _codes(pos))
        self.assertEqual(pos["effective_status"], "WILL_CONSIDER")

    def test_young_account_meeting_the_higher_minimum_passes(self):
        pos = self._position(age=4, dividend=45)
        self.assertIn("DIVIDEND-CHECK-PASS", _codes(pos))
        self.assertNotIn("DIVIDEND-CHECK-FAIL", _codes(pos))

    def test_old_account_uses_the_ordinary_minimum(self):
        pos = self._position(age=9, dividend=30)
        # no ordinary minimum on this row, so no dividend check at all
        self.assertNotIn("DIVIDEND-CHECK-FAIL", _codes(pos))
        self.assertNotIn("CREDITOR-YOUNG-ACCOUNT-DIV-UNVERIFIED", _codes(pos))

    def test_under_three_months_is_still_a_reject(self):
        pos = self._position(age=2, dividend=50)
        self.assertIn("CREDITOR-LOAN-TOO-RECENT-REJECT", _codes(pos))
        self.assertEqual(pos["effective_status"], "REJECT")

    def test_unknown_age_is_flagged_not_assumed(self):
        pos = self._position(age=None, dividend=30)
        self.assertIn("CREDITOR-YOUNG-ACCOUNT-DIV-UNVERIFIED", _codes(pos))
        self.assertNotIn("DIVIDEND-CHECK-FAIL", _codes(pos))
        self.assertEqual(pos["effective_status"], "WILL_CONSIDER")

    def test_description_mentions_the_rule(self):
        pos = self._position(age=4, dividend=45)
        self.assertIn("Accounts under 6 months old need at least 40p in the pound.", pos["checks_description"])


class RatesetterTwoTierTests(TestCase):
    """Ratesetter (confirmed 2026-10-13): 25p standard, 50p while the loan is
    under six months old. Exactly six months is "not less than six", so the
    standard 25p applies. No account-age reject: a young loan is not refused,
    it just needs the higher dividend."""

    def setUp(self):
        CreditorCriteria.objects.update_or_create(
            creditor_name="Ratesetter",
            defaults=dict(representative="NONE", status="ACCEPT", is_active=True,
                          account_age_months=None, min_dividend_pence=25,
                          young_account_months=6, young_account_min_dividend_pence=50),
        )

    def _position(self, age, dividend):
        creditor = {"creditor_name": "Ratesetter", "balance": 3000}
        if age is not None:
            creditor["account_age_months"] = age
        case = _parse_case({"creditors": [creditor]})
        case.update({"aryza_reference": "T", "client_name": "T"})
        return _check_creditor_individual(case, estimated_dividend_pence=dividend)[0]

    def test_below_six_months_needs_fifty(self):
        pos = self._position(age=5, dividend=30)
        self.assertIn("DIVIDEND-CHECK-FAIL", _codes(pos))
        self.assertIn("30p/£ < 50p/£ (account is 5 month(s) old, under 6 months)", _reason(pos, "DIVIDEND-CHECK-FAIL"))
        self.assertNotIn("CREDITOR-LOAN-TOO-RECENT-REJECT", _codes(pos))
        self.assertEqual(pos["effective_status"], "ACCEPT")
        self.assertIn("DIVIDEND-CHECK-PASS", _codes(self._position(age=5, dividend=50)))

    def test_exactly_six_months_is_standard_rate(self):
        pos = self._position(age=6, dividend=30)
        self.assertIn("DIVIDEND-CHECK-PASS", _codes(pos))
        self.assertIn("30p/£ ≥ 25p/£", _reason(pos, "DIVIDEND-CHECK-PASS"))
        self.assertNotIn("under 6 months", _reason(pos, "DIVIDEND-CHECK-PASS"))

    def test_above_six_months_is_standard_rate(self):
        pos = self._position(age=7, dividend=30)
        self.assertIn("DIVIDEND-CHECK-PASS", _codes(pos))
        self.assertIn("DIVIDEND-CHECK-FAIL", _codes(self._position(age=7, dividend=20)))

    def test_unknown_age_is_flagged_and_checked_against_the_standard_rate(self):
        pos = self._position(age=None, dividend=30)
        self.assertIn("CREDITOR-YOUNG-ACCOUNT-DIV-UNVERIFIED", _codes(pos))
        self.assertIn("at least 50p/£ while the account is under 6 months old", _reason(pos, "CREDITOR-YOUNG-ACCOUNT-DIV-UNVERIFIED"))
        self.assertIn("DIVIDEND-CHECK-PASS", _codes(pos))   # 30p meets the 25p standard; the flag asks for the age
        self.assertEqual(pos["effective_status"], "ACCEPT")
