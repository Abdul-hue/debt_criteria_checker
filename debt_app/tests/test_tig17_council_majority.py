"""
TIG-17 council majority + income/benefit deductions tests.

Excel TIG_Criteria.md: "Council Majority — MUST NOT have a deduction from
income or benefits (will reject). Case by case — check council list."

The correct condition is: fire only when BOTH council_is_majority AND
income_deductions_active.  The old code fired on council_is_majority alone,
and the message misleadingly said "Confirm whether... deductions are being
taken" when no such check was performed.

Propagation tests (Tig17CouncilPositionPropagationTests) verify that when
TIG-17 fires, the council's effective_status in council_positions is overridden
to REJECT before _compute_majority_analysis runs, so the majority calculation
reflects the true NO vote rather than the stored base status.
"""

from django.test import TestCase

from debt_app.engine.criteria import _tig_17, assess_case
from debt_app.models import CouncilRule


def _case(**over):
    base = {"council_is_majority": False, "income_deductions_active": False}
    base.update(over)
    return base


class Tig17CouncilMajorityTests(TestCase):
    def test_not_majority_passes(self):
        r = _tig_17(_case(council_is_majority=False, income_deductions_active=True))
        self.assertFalse(r.triggered)

    def test_majority_no_deductions_passes(self):
        # Council is majority but no income/benefit deductions active → no flag.
        # Old code incorrectly flagged this case.
        r = _tig_17(_case(council_is_majority=True, income_deductions_active=False))
        self.assertFalse(r.triggered)

    def test_majority_with_deductions_flags(self):
        # Council majority AND income deductions active → flag.
        r = _tig_17(_case(council_is_majority=True, income_deductions_active=True))
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        # Message must NOT say "Confirm whether" (deductions are confirmed active)
        self.assertNotIn("Confirm whether", r.message)
        self.assertIn("deduction", r.message.lower())

    def test_not_majority_with_deductions_passes(self):
        r = _tig_17(_case(council_is_majority=False, income_deductions_active=True))
        self.assertFalse(r.triggered)


def _council_case(income_deductions_active=True):
    """Minimal assess_case payload for TIG-17 propagation tests.

    Council creditor holds 80 % of total debt (£4 000 of £5 000) so
    council_is_majority=True fires reliably without touching any HMRC path.
    The creditor name contains "council" — the heuristic used by _parse_case.
    """
    return {
        "creditors": [
            {
                "name": "Zzyborough District Council",
                "creditor_type": "council_tax",
                "balance": 4000.0,
            },
            {
                "name": "Generic Lender",
                "creditor_type": "personal_loan",
                "balance": 1000.0,
            },
        ],
        "income_deductions_active": income_deductions_active,
        "financial_summary": {"net_balance": 200},
        "documents": [],
        "gold_transactions": [],
        "evidence_ledger": [],
    }


class Tig17CouncilPositionPropagationTests(TestCase):
    """assess_case must propagate TIG-17 into council_positions before
    _compute_majority_analysis so the majority calculation reflects the true
    NO vote rather than the council's stored base status.

    Uses a synthetic CouncilRule with status=WILL_CONSIDER — the value that
    would silently count as a YES vote without the propagation fix. This also
    validates the casing guard: 'WILL_CONSIDER' is already uppercase in the DB,
    so the .upper() in the guard is a no-op and the override must still fire.
    """

    def setUp(self):
        CouncilRule.objects.create(
            council_name="Zzyborough District Council",
            status="WILL_CONSIDER",
        )

    def _council_position(self, result):
        return next(
            (cp for cp in result["council_positions"]
             if "Zzyborough" in cp.get("creditor_name", "")),
            None,
        )

    def test_will_consider_overridden_to_reject_when_tig17_fires(self):
        # WILL_CONSIDER is the exact status that would be counted as a YES vote
        # without the fix. Verify the override fires on it (casing guard check).
        result = assess_case(_council_case(income_deductions_active=True),
                             detected_representatives=set())
        cp = self._council_position(result)
        self.assertIsNotNone(cp, "Zzyborough must appear in council_positions")
        self.assertEqual(cp["effective_status"], "REJECT")
        codes = [f.get("code") for f in cp.get("findings", [])]
        self.assertIn("COUNCIL-TIG17-INCOME-DEDUCTION", codes)
        # The rule code itself belongs only in the structured `codes` list above —
        # the human-readable `reason` text should describe the situation in plain
        # English rather than referencing the internal rule code.
        self.assertIn("income", cp.get("reason", "").lower())

    def test_majority_analysis_does_not_count_council_as_yes(self):
        # With the council overridden to REJECT, it must not contribute to
        # voting_debt. The only remaining creditor (£1 000 of £5 000 total)
        # cannot reach the 75 % threshold → majority not achievable.
        result = assess_case(_council_case(income_deductions_active=True),
                             detected_representatives=set())
        ma = result["majority_analysis"]
        # Council's £4 000 must NOT be in voting_debt.
        self.assertLess(float(ma["voting_debt"]), float(ma["threshold"]))

    def test_no_override_when_no_income_deductions(self):
        # No income deductions → TIG-17 does not fire → effective_status stays
        # at the council's base WILL_CONSIDER.
        result = assess_case(_council_case(income_deductions_active=False),
                             detected_representatives=set())
        cp = self._council_position(result)
        self.assertIsNotNone(cp)
        self.assertEqual(cp["effective_status"], "WILL_CONSIDER")
        codes = [f.get("code") for f in cp.get("findings", [])]
        self.assertNotIn("COUNCIL-TIG17-INCOME-DEDUCTION", codes)

    def test_reject_status_not_double_overridden(self):
        # A council already at REJECT (e.g. has its own reject rule) must not
        # gain a spurious TIG-17 finding on top.
        CouncilRule.objects.filter(council_name="Zzyborough District Council").update(
            status="REJECT"
        )
        result = assess_case(_council_case(income_deductions_active=True),
                             detected_representatives=set())
        cp = self._council_position(result)
        self.assertIsNotNone(cp)
        self.assertEqual(cp["effective_status"], "REJECT")
        codes = [f.get("code") for f in cp.get("findings", [])]
        self.assertNotIn("COUNCIL-TIG17-INCOME-DEDUCTION", codes)
