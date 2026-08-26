"""
Majority threshold base: abstaining creditors are excluded from the 75%.

EXCEL_CRITERIA_REFERENCE.md defines DO_NOT_VOTE as "Creditor submits proof of
debt but does not vote", and its Council Majority rule fails a case only when
councils "are likely to vote NO and represent >25% of debt by value". An
abstention is not a NO, so a non-voting creditor's balance must come out of the
75% base as well as out of voting_debt.

Previously the threshold was 75% of ALL unsecured debt while non-voters were
excluded from the numerator only. That made the threshold unreachable by
construction whenever abstaining creditors held more than a quarter of the
book, raising a false MAJORITY-IMPOSSIBLE on cases that a real creditors'
meeting would approve (observed on a case where a DO_NOT_VOTE council held 26%
of the debt and every voting creditor supported the IVA). MAJORITY-IMPOSSIBLE
is now a referral flag rather than a hard block — see
test_majority_impossible_is_referral — but that is its SEVERITY; these tests
cover the threshold arithmetic that decides whether it fires at all.

REJECT creditors are unaffected: they DO vote, so they stay in the base and
must still be able to defeat the majority.
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


def _analyse(rows, total_debt, extra_creditors=()):
    creditors = [_creditor(i, n, b) for i, n, b, _ in rows]
    creditors.extend(extra_creditors)
    return _compute_majority_analysis(
        {"creditors": creditors, "total_debt": total_debt},
        [_position(i, n, s) for i, n, _, s in rows],
    )


class MajorityVotingPoolTests(TestCase):
    def test_abstaining_council_excluded_from_threshold_base(self):
        # Real shape of the case this fixed: a DO_NOT_VOTE council holding 26%
        # of a £6,986.76 book, with every voting creditor supporting the IVA.
        rows = [
            (0, "Basildon Borough Council", 1830.76, "DO_NOT_VOTE"),
            (1, "Tesco Mobile", 23.00, "DO_NOT_VOTE"),
            (2, "Barclays Bank Plc", 611.00, "ACCEPT"),
            (3, "Lowell Financial", 35.00, "ACCEPT"),
            (4, "British Telecom", 486.00, "UNKNOWN"),
            (5, "Capital One", 3163.00, "ACCEPT"),
            (6, "Lendable Limited", 441.00, "ACCEPT"),
            (7, "NewDay", 397.00, "ACCEPT"),
        ]
        ma = _analyse(rows, 6986.76)

        # £1,853.76 of abstaining debt comes out of the base.
        self.assertEqual(ma["voting_pool"], Decimal("5133.00"))
        self.assertEqual(ma["threshold"], Decimal("3849.75"))
        # total_debt still reports the FULL unsecured book — other rules
        # (e.g. CREDITOR-UNIDENTIFIED-MATERIAL) take percentages off it.
        self.assertEqual(ma["total_debt"], Decimal("6986.76"))

        # £4,647 of confirmed support clears £3,849.75 → no block.
        self.assertEqual(ma["voting_debt"], Decimal("4647.00"))
        self.assertTrue(ma["achievable"])
        self.assertFalse(ma["indeterminate"])

    def test_rejecting_council_still_defeats_majority(self):
        # A council that VOTES NO stays in the base and must still block:
        # £1,000 of support against a £3,750 threshold.
        ma = _analyse(
            [(0, "Council", 4000, "REJECT"), (1, "Other", 1000, "ACCEPT")],
            5000,
        )
        self.assertEqual(ma["voting_pool"], Decimal("5000"))
        self.assertEqual(ma["threshold"], Decimal("3750.00"))
        self.assertFalse(ma["achievable"])
        # Not indeterminate: unreachable even counting every undecided
        # creditor as a yes, so it takes the MAJORITY-IMPOSSIBLE branch.
        self.assertFalse(ma["indeterminate"])

    def test_unknown_creditor_stays_in_base(self):
        # UNKNOWN is not an abstention — the vote is genuinely unresolved, so
        # the balance must stay in the base and be reported as could-flip.
        ma = _analyse(
            [(0, "Unmatched Creditor", 3000, "UNKNOWN"), (1, "Other", 1000, "ACCEPT")],
            4000,
        )
        self.assertEqual(ma["voting_pool"], Decimal("4000"))
        self.assertEqual(ma["unknown_debt"], Decimal("3000"))
        self.assertFalse(ma["achievable"])
        # Identifying it could still reach the threshold → flag, not block.
        self.assertTrue(ma["indeterminate"])

    def test_all_creditors_abstaining_does_not_block(self):
        # No votes to count means no majority to compute; don't manufacture a
        # hard block out of an empty pool.
        ma = _analyse(
            [(0, "A", 1000, "DO_NOT_VOTE"), (1, "B", 500, "DO_NOT_VOTE")],
            1500,
        )
        self.assertEqual(ma["voting_pool"], Decimal("0"))
        self.assertEqual(ma["threshold"], Decimal("0.00"))
        self.assertTrue(ma["achievable"])

    def test_secured_debt_never_enters_the_base(self):
        # `total_debt` is unsecured-only but `creditors` also carries secured
        # rows, so the abstaining subtrahend must skip secured debt or a
        # mortgage would distort the base.
        ma = _analyse(
            [(0, "Council", 3000, "DO_NOT_VOTE"), (1, "Lender", 1000, "ACCEPT")],
            4000,
            extra_creditors=[_creditor(2, "Mortgage Co", 150000, secured=True)],
        )
        self.assertEqual(ma["voting_pool"], Decimal("1000"))
        self.assertEqual(ma["threshold"], Decimal("750.00"))
        self.assertTrue(ma["achievable"])

    def test_zero_total_debt_returns_voting_pool_key(self):
        # The early-return branch must carry the same keys as the main path —
        # callers read voting_pool unconditionally when building rule messages.
        ma = _compute_majority_analysis({"creditors": [], "total_debt": 0}, [])
        self.assertIn("voting_pool", ma)
        self.assertEqual(ma["voting_pool"], Decimal("0"))
        self.assertTrue(ma["achievable"])
