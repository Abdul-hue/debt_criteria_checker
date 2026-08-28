"""
Regression test for the EE bug: a creditor that matched no CreditorCriteria
row at all (effective_status UNKNOWN, findings=[CREDITOR-UNKNOWN]) must never
be promoted to a representative-body status/reason by
_apply_representative_outcomes. Doing so silently contradicts the "no
matching record" finding, producing e.g. REJECT + a rule-derived reason next
to a finding that says the creditor was never matched.
"""

from django.test import TestCase

from debt_app.engine.criteria import _apply_representative_outcomes


def _unmatched_position(representative="NONE"):
    """Mirrors the dict shape built in _check_creditor_individual's
    CreditorCriteria.DoesNotExist branch for a genuinely unmatched creditor."""
    return {
        "creditor_name": "EE",
        "representative": representative,
        "effective_status": "UNKNOWN",
        "findings": [{
            "code": "CREDITOR-UNKNOWN",
            "reason": "This creditor has no matching record in our database.",
        }],
        "reason": "This creditor has no matching record in our database.",
        "rule_ids": ["CREDITOR-UNKNOWN"],
    }


class ApplyRepresentativeOutcomesUnknownGuardTests(TestCase):
    def test_unmatched_creditor_not_promoted_to_reject(self):
        positions = [_unmatched_position(representative="TIX")]
        outcomes = {
            "TIX": {
                "status": "REJECT",
                "rule_id": "TIX-1",
                "message": "Reject all IVA's regardless of vulnerabilities of the client.",
            }
        }

        _apply_representative_outcomes(positions, outcomes)

        pos = positions[0]
        self.assertEqual(pos["effective_status"], "UNKNOWN")
        self.assertEqual(
            pos["reason"], "This creditor has no matching record in our database."
        )
        self.assertIn(
            {"code": "CREDITOR-UNKNOWN", "reason": "This creditor has no matching record in our database."},
            pos["findings"],
        )
        self.assertEqual(len(pos["findings"]), 1)

    def test_unmatched_creditor_not_promoted_to_accept(self):
        positions = [_unmatched_position(representative="WATCH")]
        outcomes = {"WATCH": {"status": "ACCEPT", "rule_id": None, "message": None}}

        _apply_representative_outcomes(positions, outcomes)

        pos = positions[0]
        self.assertEqual(pos["effective_status"], "UNKNOWN")
        self.assertEqual(
            pos["reason"], "This creditor has no matching record in our database."
        )

    def test_matched_creditor_still_gets_representative_outcome(self):
        """Sanity check: the guard is scoped to CREDITOR-UNKNOWN, not to UNKNOWN
        in general — a real PENDING_REP_OUTCOME position must still be stamped."""
        positions = [{
            "creditor_name": "Watch Lender Test",
            "representative": "WATCH",
            "effective_status": "PENDING_REP_OUTCOME",
            "findings": [],
            "reason": "",
            "rule_ids": [],
            "checks_description": "Watch Lender Test: WATCH representative creditor.",
        }]
        outcomes = {"WATCH": {"status": "WILL_CONSIDER", "rule_id": "WATCH-22.6", "message": "flag"}}

        _apply_representative_outcomes(positions, outcomes)

        pos = positions[0]
        self.assertEqual(pos["effective_status"], "WILL_CONSIDER")
        self.assertTrue(any(f.get("code") == "WATCH-WILL_CONSIDER" for f in pos["findings"]))
