"""
MAJORITY-IMPOSSIBLE is a REFERRAL flag, not a hard block.

An unreachable 75% is a fact about the creditor book, not a defect in the case,
and the engine's view of who votes is an ESTIMATE assembled from stored
creditor positions: a creditor can vote against type, a representative body can
be re-canvassed, and balances get corrected. Hard-blocking took the decision
away from the caseworker, so the rule now surfaces for review and a human
decides whether to abandon or press on.

The MATHS is deliberately unchanged — this branch is still only reached when the
threshold cannot be met even counting EVERY undecided creditor as a yes; the
`indeterminate` case still takes the other branch. See test_majority_voting_pool
for the threshold behaviour, which this must not disturb.
"""

from django.test import TestCase

from debt_app.engine.criteria import assess_case
from debt_app.models import CouncilRule


def _get(entry, field):
    """assess_case returns RuleResult OBJECTS; the same lists arrive as dicts
    once serialised through the API. Read either shape so the test asserts the
    engine's behaviour rather than its transport format."""
    if isinstance(entry, dict):
        return entry.get(field)
    return getattr(entry, field, None)


def _rule_ids(entries):
    return [_get(e, 'rule_id') for e in (entries or [])]


def _find(entries, rule_id):
    return next((e for e in (entries or []) if _get(e, 'rule_id') == rule_id), None)


class MajorityImpossibleIsAReferralTests(TestCase):
    """A council that VOTES NO and holds 80% of the book makes the 75%
    unreachable even if every other creditor says yes."""

    def setUp(self):
        CouncilRule.objects.create(
            council_name="Zzyborough District Council",
            status="REJECT",
        )

    def _result(self):
        return assess_case({
            "creditors": [
                {"name": "Zzyborough District Council",
                 "creditor_type": "council_tax", "balance": 4000.0},
                {"name": "Generic Lender",
                 "creditor_type": "personal_loan", "balance": 1000.0},
            ],
            "financial_summary": {"net_balance": 200},
            "documents": [],
            "gold_transactions": [],
            "evidence_ledger": [],
        }, detected_representatives=set())

    def test_the_majority_really_is_unreachable_in_this_case(self):
        # Guard the fixture: if this stops being an impossible majority the
        # assertions below would pass for the wrong reason.
        ma = self._result()["majority_analysis"]
        self.assertFalse(ma["achievable"])
        self.assertFalse(ma["indeterminate"],
                         "must be the IMPOSSIBLE branch, not INDETERMINATE")

    def test_it_is_raised_as_a_flag(self):
        result = self._result()
        self.assertIn('MAJORITY-IMPOSSIBLE', _rule_ids(result.get('flags')))

    def test_it_is_not_a_hard_block(self):
        result = self._result()
        self.assertNotIn('MAJORITY-IMPOSSIBLE', _rule_ids(result.get('hard_blocks')),
                         "an unreachable majority must not auto-refuse the case; "
                         "the caseworker decides")

    def test_its_severity_says_flag(self):
        # The Remedials panel and the Send-to-Manager gate both read severity,
        # so the field has to agree with which list it landed in.
        entry = _find(self._result().get('flags'), 'MAJORITY-IMPOSSIBLE')
        self.assertIsNotNone(entry)
        self.assertEqual(_get(entry, 'severity'), 'flag')

    def test_the_message_asks_for_review_rather_than_refusing(self):
        entry = _find(self._result().get('flags'), 'MAJORITY-IMPOSSIBLE')
        self.assertIn('review', (_get(entry, 'message') or '').lower())

    def test_the_case_is_not_reported_as_blocked_by_this_rule(self):
        # `overall` is computed BEFORE the majority rules run, so moving this
        # rule to `flags` must still lift a clean pass to "flagged" rather than
        # leaving it reporting "pass" while carrying a flag.
        result = self._result()
        self.assertIn(result.get('overall'), ('flagged', 'blocked'))
        if not _rule_ids(result.get('hard_blocks')):
            self.assertEqual(result.get('overall'), 'flagged',
                             "no hard blocks left, so the case should be flagged")
