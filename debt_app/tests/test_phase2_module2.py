"""
Phase 2 Module 2 tests: Recent Spend Engine — assessment_date-relative time windows.

The rules TIX-01 (Shop Direct spend last 3 months) and TIX-03 (Creation spend last
4 months) must use the case's assessment_date as the reference point, not date.today().
Same applies to total_spend_2mo and car_finance_tx_3mo.

Source of truth: TIP CRITERIA & VOTING HISTORY.xlsx
  - TIX Criteria tab: TIX-01 "any transactions in the last 3 months"
  - TIX Criteria tab: TIX-03 "any transactions in the last 4 months"
"""

from datetime import date, timedelta

from django.test import SimpleTestCase

from debt_app.criteria_engine import (
    _days_since,
    _is_within_days,
    _parse_case,
    _recent_transactions_matching,
    _tix_01,
    _tix_03,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tx(description: str, days_before_assessment: int, assessment_date: date) -> dict:
    """Build a synthetic gold_transaction placed N days before assessment_date."""
    tx_date = assessment_date - timedelta(days=days_before_assessment)
    return {
        "description": description,
        "amount": -50.0,
        "transaction_type": "money_out",
        "transaction_date": tx_date.isoformat(),
    }


def _minimal_payload(assessment_date: str, creditors=None, transactions=None) -> dict:
    return {
        "assessment_date": assessment_date,
        "creditors": creditors or [
            {"creditor_name": "Shop Direct", "balance": 500, "creditor_type": "store_card"}
        ],
        "financial_summary": {"net_balance": 300, "total_income": 1800},
        "gold_transactions": transactions or [],
    }


# ---------------------------------------------------------------------------
# _days_since: reference param
# ---------------------------------------------------------------------------

class TestDaysSinceReference(SimpleTestCase):
    """_days_since must use reference date when supplied, not today."""

    def test_reference_date_used(self):
        ref = date(2024, 6, 1)
        tx_date = "2024-05-01"  # 31 days before ref
        self.assertEqual(_days_since(tx_date, reference=ref), 31)

    def test_today_used_when_no_reference(self):
        # A date far in the past — result > 0 regardless of when the test runs
        result = _days_since("2000-01-01")
        self.assertGreater(result, 365)

    def test_missing_date_returns_9999(self):
        self.assertEqual(_days_since(None, reference=date(2024, 1, 1)), 9999)
        self.assertEqual(_days_since("", reference=date(2024, 1, 1)), 9999)

    def test_invalid_date_returns_9999(self):
        self.assertEqual(_days_since("not-a-date", reference=date(2024, 1, 1)), 9999)

    def test_future_transaction_relative_to_reference_returns_negative(self):
        ref = date(2024, 6, 1)
        tx_date = "2024-06-15"  # 14 days AFTER ref
        self.assertEqual(_days_since(tx_date, reference=ref), -14)

    def test_is_within_days_uses_reference(self):
        ref = date(2024, 6, 1)
        tx_80_days_before = (ref - timedelta(days=80)).isoformat()
        self.assertTrue(_is_within_days(tx_80_days_before, 90, reference=ref))
        self.assertFalse(_is_within_days(tx_80_days_before, 70, reference=ref))


# ---------------------------------------------------------------------------
# _recent_transactions_matching: reference param
# ---------------------------------------------------------------------------

class TestRecentTransactionsMatchingReference(SimpleTestCase):
    """_recent_transactions_matching must apply within_days relative to reference."""

    def test_transaction_85_days_before_reference_included_in_90_day_window(self):
        ref = date(2024, 6, 1)
        tx = _tx("very.co.uk payment", 85, ref)
        result = _recent_transactions_matching([tx], ["very"], 90, reference=ref)
        self.assertEqual(len(result), 1)

    def test_transaction_95_days_before_reference_excluded_from_90_day_window(self):
        ref = date(2024, 6, 1)
        tx = _tx("very.co.uk payment", 95, ref)
        result = _recent_transactions_matching([tx], ["very"], 90, reference=ref)
        self.assertEqual(len(result), 0)

    def test_keyword_matching_is_case_insensitive(self):
        ref = date(2024, 6, 1)
        tx = _tx("SHOP DIRECT ORDER", 10, ref)
        result = _recent_transactions_matching([tx], ["shop direct"], 90, reference=ref)
        self.assertEqual(len(result), 1)

    def test_no_transactions_returns_empty(self):
        ref = date(2024, 6, 1)
        result = _recent_transactions_matching([], ["very"], 90, reference=ref)
        self.assertEqual(result, [])

    def test_non_matching_description_excluded(self):
        ref = date(2024, 6, 1)
        tx = _tx("tesco groceries", 10, ref)
        result = _recent_transactions_matching([tx], ["very", "shop direct"], 90, reference=ref)
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# _parse_case: spend windows relative to assessment_date
# ---------------------------------------------------------------------------

class TestParseCaseSpendWindows(SimpleTestCase):
    """_parse_case spend windows must be measured from assessment_date, not today."""

    def test_shop_direct_tx_3mo_uses_assessment_date(self):
        """A transaction 80 days before assessment_date should appear in shop_direct_tx_3mo."""
        assessment = date(2024, 6, 1)
        tx = _tx("shop direct", 80, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["shop_direct_tx_3mo"]), 1)

    def test_shop_direct_tx_outside_window_excluded(self):
        """A transaction 100 days before assessment_date is outside the 90-day window."""
        assessment = date(2024, 6, 1)
        tx = _tx("shop direct", 100, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["shop_direct_tx_3mo"]), 0)

    def test_very_alias_included_in_shop_direct_window(self):
        """'very' keyword hits _SHOP_DIRECT_NAMES and is caught within 3-month window."""
        assessment = date(2024, 6, 1)
        tx = _tx("very.co.uk online", 45, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["shop_direct_tx_3mo"]), 1)

    def test_creation_tx_4mo_uses_assessment_date(self):
        """A transaction 100 days before assessment_date should appear in creation_tx_4mo (120-day window)."""
        assessment = date(2024, 6, 1)
        tx = _tx("creation financial services", 100, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["creation_tx_4mo"]), 1)

    def test_creation_tx_outside_4mo_window_excluded(self):
        """A transaction 130 days before assessment_date is outside the 120-day window."""
        assessment = date(2024, 6, 1)
        tx = _tx("creation financial services", 130, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["creation_tx_4mo"]), 0)

    def test_sygma_alias_included_in_creation_window(self):
        assessment = date(2024, 6, 1)
        tx = _tx("sygma bank payment", 60, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["creation_tx_4mo"]), 1)

    def test_total_spend_2mo_uses_assessment_date(self):
        """total_spend_2mo sums money_out transactions within 60 days of assessment_date."""
        assessment = date(2024, 6, 1)
        recent = _tx("amazon purchase", 30, assessment)
        old = _tx("amazon purchase", 70, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[recent, old],
        )
        c = _parse_case(payload)
        # Only the 30-day-old transaction should count
        self.assertAlmostEqual(c["total_spend_2mo"], 50.0, places=2)

    def test_car_finance_tx_3mo_uses_assessment_date(self):
        """car_finance_tx_3mo uses 90-day window from assessment_date."""
        assessment = date(2024, 6, 1)
        tx_in = _tx("car finance monthly", 60, assessment)
        tx_out = _tx("car finance monthly", 100, assessment)
        payload = _minimal_payload(
            assessment_date=assessment.isoformat(),
            transactions=[tx_in, tx_out],
        )
        c = _parse_case(payload)
        self.assertEqual(len(c["car_finance_tx_3mo"]), 1)

    def test_historical_case_does_not_pick_up_recent_transactions(self):
        """For a historical case (assessment_date far in the past), transactions from
        today should NOT appear in the spend windows."""
        # Assessment date 2 years ago
        old_assessment = date.today() - timedelta(days=730)
        # Transaction dated today — 730+ days AFTER assessment_date
        today_tx = {
            "description": "shop direct order",
            "amount": -75.0,
            "transaction_type": "money_out",
            "transaction_date": date.today().isoformat(),
        }
        payload = _minimal_payload(
            assessment_date=old_assessment.isoformat(),
            transactions=[today_tx],
        )
        c = _parse_case(payload)
        # The today transaction is 730 days AFTER the assessment_date, so _days_since
        # returns a negative number — should NOT be in the 90-day window
        self.assertEqual(len(c["shop_direct_tx_3mo"]), 0)


# ---------------------------------------------------------------------------
# TIX-01 / TIX-03 end-to-end with assessment_date
# ---------------------------------------------------------------------------

class TestTixRulesHistoricalAssessment(SimpleTestCase):
    """TIX-01 and TIX-03 results depend on assessment_date-relative windows."""

    def _run_tix_01(self, assessment_date: date, tx_days_ago: int) -> bool:
        """Return True if TIX-01 triggers given a single Shop Direct transaction."""
        tx = _tx("very.co.uk order", tx_days_ago, assessment_date)
        payload = _minimal_payload(
            assessment_date=assessment_date.isoformat(),
            transactions=[tx],
        )
        c = _parse_case(payload)
        result = _tix_01(c)
        return result.triggered

    def test_tix_01_triggers_when_tx_within_90_days_of_assessment(self):
        assessment = date(2024, 6, 1)
        self.assertTrue(self._run_tix_01(assessment, tx_days_ago=80))

    def test_tix_01_does_not_trigger_when_tx_outside_90_days_of_assessment(self):
        assessment = date(2024, 6, 1)
        self.assertFalse(self._run_tix_01(assessment, tx_days_ago=100))

    def test_tix_01_historical_case_not_polluted_by_present_day_transactions(self):
        """Historical assessment should not be blocked by Shop Direct transactions
        that happened after the assessment date."""
        old_assessment = date(2023, 1, 1)
        # Transaction dated 6 months AFTER the assessment date
        future_tx = {
            "description": "shop direct order",
            "amount": -40.0,
            "transaction_type": "money_out",
            "transaction_date": "2023-07-01",
        }
        payload = _minimal_payload(
            assessment_date=old_assessment.isoformat(),
            transactions=[future_tx],
        )
        c = _parse_case(payload)
        result = _tix_01(c)
        self.assertFalse(result.triggered)

    def _run_tix_03(self, assessment_date: date, tx_days_ago: int) -> bool:
        tx = _tx("sygma bank ltd", tx_days_ago, assessment_date)
        payload = _minimal_payload(
            assessment_date=assessment_date.isoformat(),
            creditors=[{"creditor_name": "Creation Consumer Finance", "balance": 400, "creditor_type": "store_card"}],
            transactions=[tx],
        )
        c = _parse_case(payload)
        result = _tix_03(c)
        return result.triggered

    def test_tix_03_triggers_when_tx_within_120_days_of_assessment(self):
        assessment = date(2024, 6, 1)
        self.assertTrue(self._run_tix_03(assessment, tx_days_ago=110))

    def test_tix_03_does_not_trigger_when_tx_outside_120_days_of_assessment(self):
        assessment = date(2024, 6, 1)
        self.assertFalse(self._run_tix_03(assessment, tx_days_ago=130))
