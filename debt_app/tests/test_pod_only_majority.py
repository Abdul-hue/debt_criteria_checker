"""
Regression test: POD_ONLY creditors must be excluded from the 75% majority
voting-pool denominator exactly like DO_NOT_VOTE.

A creditor with POD_ONLY status submits a proof of debt but does not cast a
vote at the meeting.  Their balance must therefore come OUT of both the
numerator (voting_debt) and the denominator (voting_pool / 75% base) so that
the majority threshold remains achievable for the voting creditors.
"""

from decimal import Decimal

from django.test import TestCase

from debt_app.engine.criteria import _compute_majority_analysis


def _creditor(idx, name, balance, secured=False):
    return {
        "_idx": idx,
        "name": name,
        "original_name": name,
        "balance": float(balance),
        "crm_balance": Decimal(str(balance)),
        "is_secured": secured,
    }


def _position(idx, name, status):
    return {
        "creditor_name": name,
        "effective_status": status,
        "_creditor_idx": idx,
        "balance": 0,
    }


def _analyse(rows, total_debt):
    creditors = [_creditor(i, n, b) for i, n, b, _ in rows]
    return _compute_majority_analysis(
        {"creditors": creditors, "total_debt": total_debt},
        [_position(i, n, s) for i, n, _, s in rows],
    )


class PodOnlyMajorityDenominatorTests(TestCase):

    def test_pod_only_excluded_from_denominator(self):
        """POD_ONLY creditor holding 26% of book: every other voter says YES
        and the case should be achievable, mirroring the DO_NOT_VOTE behaviour."""
        rows = [
            (0, "Local Authority Council", 1853.76, "POD_ONLY"),
            (1, "Barclays Bank Plc",        611.00,  "ACCEPT"),
            (2, "Capital One",             3163.00,  "ACCEPT"),
            (3, "Lendable Limited",          441.00,  "ACCEPT"),
            (4, "NewDay",                    397.00,  "ACCEPT"),
        ]
        total = sum(b for _, _, b, _ in rows)
        ma = _analyse(rows, total)

        # POD_ONLY balance must be subtracted from voting_pool
        self.assertEqual(ma["voting_pool"], Decimal(str(total - 1853.76)))
        # All other creditors accept -> achievable
        self.assertTrue(ma["achievable"])

    def test_pod_only_threshold_is_75_pct_of_voting_pool(self):
        """Threshold = 75% of voting_pool, NOT of total_debt."""
        rows = [
            (0, "Council",   2000, "POD_ONLY"),
            (1, "Creditor A", 500, "ACCEPT"),
            (2, "Creditor B", 500, "ACCEPT"),
        ]
        ma = _analyse(rows, 3000)
        self.assertEqual(ma["voting_pool"], Decimal("1000"))
        self.assertEqual(ma["threshold"], Decimal("750.00"))
        self.assertTrue(ma["achievable"])

    def test_do_not_vote_still_excluded(self):
        """Existing DO_NOT_VOTE behaviour is unaffected."""
        rows = [
            (0, "Non-voter", 1000, "DO_NOT_VOTE"),
            (1, "Acceptor",  3000, "ACCEPT"),
        ]
        ma = _analyse(rows, 4000)
        self.assertEqual(ma["voting_pool"], Decimal("3000"))
        self.assertTrue(ma["achievable"])

    def test_reject_stays_in_denominator(self):
        """A REJECT creditor votes NO and must stay in the base."""
        rows = [
            (0, "Rejecter",  3000, "REJECT"),
            (1, "Acceptor",  1000, "ACCEPT"),
        ]
        ma = _analyse(rows, 4000)
        self.assertEqual(ma["voting_pool"], Decimal("4000"))
        self.assertFalse(ma["achievable"])
