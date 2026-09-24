"""
Regression tests for the Gambling transaction classification fix.

Fix: transaction category="Gambling" (case-insensitive) is now authoritative;
keyword scan of description is the fallback for uncategorised transactions.
If no transactions are present but gambling_transactions_total is provided
in the case JSON, that total is used as gambling_monthly.
"""

from datetime import date, timedelta
from django.test import TestCase
from debt_app.engine.criteria import _gambling_monthly, _gambling_all_transactions


def _tx(description, amount, category=None, days_ago=5, reference=None):
    ref = reference or date.today()
    tx_date = (ref - timedelta(days=days_ago)).isoformat()
    t = {
        "description": description,
        "amount": amount,
        "transaction_type": "money_out",
        "transaction_date": tx_date,
    }
    if category is not None:
        t["category"] = category
    return t


class GamblingCategoryTests(TestCase):

    def test_category_gambling_is_authoritative(self):
        """A transaction with category='Gambling' is counted even if description has no keyword."""
        txs = [_tx("DIRECT DEBIT REF12345", -50.0, category="Gambling")]
        total = _gambling_monthly(txs, reference=date.today())
        self.assertAlmostEqual(total, 50.0)

    def test_category_gambling_case_insensitive(self):
        txs = [_tx("PAYMENT OUT", -75.0, category="gambling")]
        total = _gambling_monthly(txs, reference=date.today())
        self.assertAlmostEqual(total, 75.0)

    def test_keyword_fallback_when_no_category(self):
        """No category field — description keyword should still detect gambling."""
        txs = [_tx("Betfair withdrawal", -30.0)]
        total = _gambling_monthly(txs, reference=date.today())
        self.assertAlmostEqual(total, 30.0)

    def test_non_gambling_category_not_counted(self):
        """category='Food' — must not be counted even if description has gambling keyword."""
        txs = [_tx("bet restaurant payment", -20.0, category="Food")]
        total = _gambling_monthly(txs, reference=date.today())
        self.assertAlmostEqual(total, 0.0)

    def test_old_30_day_window_respected(self):
        """Transactions older than 30 days must not be counted."""
        txs = [_tx("Betfair", -100.0, category="Gambling", days_ago=45)]
        total = _gambling_monthly(txs, reference=date.today())
        self.assertAlmostEqual(total, 0.0)

    def test_all_transactions_includes_category_flagged(self):
        """_gambling_all_transactions must include category-flagged transactions of any age."""
        txs = [
            _tx("DIRECT DEBIT REF99", -200.0, category="Gambling", days_ago=90),
        ]
        result = _gambling_all_transactions(txs)
        self.assertEqual(len(result), 1)
