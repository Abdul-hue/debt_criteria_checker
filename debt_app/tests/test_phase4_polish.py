"""
Phase 4 Polish — tests for newly activated rules:

  TIG-03   SFS guideline expenditure breach → flag
  TIG-04   DLA/PIP income with no disability expenses → flag
  WATCH-22.1  Vulnerability claimed without evidence → flag + "Speak to Tom/Debra"
  TIX-06   Same, TIX representative
  EVOLVE-03  Same, EVOLVE representative
"""

from django.test import TestCase

from debt_app.criteria_engine import (
    _tig_03,
    _tig_04,
    _watch_22_1,
    _tix_06,
    _evolve_03,
    _parse_case,
    assess_case,
)
from debt_app.tests.test_phase3 import _minimal_old_payload


def _base():
    return _parse_case(_minimal_old_payload())


def _assess(detected_reps=None, **overrides):
    payload = _minimal_old_payload()
    payload.update(overrides)
    return assess_case(payload, detected_representatives=detected_reps)


def _rule_ids(lst):
    return [r.rule_id for r in lst]


# ---------------------------------------------------------------------------
# TIG-03: SFS guideline expenditure
# ---------------------------------------------------------------------------

class TestTIG03SFS(TestCase):

    def test_no_sfs_data_is_pass(self):
        c = _base()
        c["sfs_expenditure_breakdown"] = None
        r = _tig_03(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-03")

    def test_all_within_guidelines_is_pass(self):
        c = _base()
        c["sfs_expenditure_breakdown"] = {"food": False, "transport": False, "clothing": False}
        r = _tig_03(c)
        self.assertFalse(r.triggered)

    def test_single_breach_is_flag(self):
        c = _base()
        c["sfs_expenditure_breakdown"] = {"food": False, "transport": True, "clothing": False}
        r = _tig_03(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertIn("transport", r.message)

    def test_multiple_breaches_listed_in_message(self):
        c = _base()
        c["sfs_expenditure_breakdown"] = {"food": True, "transport": True, "clothing": False}
        r = _tig_03(c)
        self.assertTrue(r.triggered)
        self.assertIn("food", r.message)
        self.assertIn("transport", r.message)

    def test_flows_through_assess_case(self):
        result = _assess(sfs_expenditure_breakdown={"transport": True})
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("TIG-03", flag_ids)

    def test_absent_field_is_pass_not_todo_stub(self):
        result = _assess()
        all_ids = (
            _rule_ids(result["hard_blocks"])
            + _rule_ids(result["flags"])
            + _rule_ids(result["info"])
            + _rule_ids(result["passed"])
        )
        for rid in all_ids:
            self.assertFalse(rid.startswith("TODO-"), msg=f"Unexpected TODO stub: {rid}")


# ---------------------------------------------------------------------------
# TIG-04: DLA/PIP income without disability expenses
# ---------------------------------------------------------------------------

class TestTIG04Disability(TestCase):

    def test_no_disability_income_is_pass(self):
        c = _base()
        c["disability_income"] = None
        c["disability_expenses"] = None
        r = _tig_04(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-04")

    def test_disability_income_with_expenses_is_pass(self):
        c = _base()
        c["disability_income"] = 300.0
        c["disability_expenses"] = 250.0
        r = _tig_04(c)
        self.assertFalse(r.triggered)

    def test_disability_income_without_expenses_is_flag(self):
        c = _base()
        c["disability_income"] = 300.0
        c["disability_expenses"] = None
        r = _tig_04(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "TIG-04")

    def test_disability_income_zero_expenses_is_flag(self):
        c = _base()
        c["disability_income"] = 200.0
        c["disability_expenses"] = 0
        r = _tig_04(c)
        self.assertTrue(r.triggered)

    def test_flows_through_assess_case(self):
        result = _assess(disability_income=400.0, disability_expenses=None)
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("TIG-04", flag_ids)

    def test_absent_both_fields_no_todo_stub(self):
        result = _assess()
        all_ids = (
            _rule_ids(result["hard_blocks"])
            + _rule_ids(result["flags"])
            + _rule_ids(result["info"])
            + _rule_ids(result["passed"])
        )
        for rid in all_ids:
            self.assertFalse(rid.startswith("TODO-"), msg=f"Unexpected TODO stub: {rid}")


# ---------------------------------------------------------------------------
# WATCH-22.1, TIX-06, EVOLVE-03: Vulnerability "Speak to Tom/Debra"
# ---------------------------------------------------------------------------

class TestVulnerabilityRules(TestCase):

    def _vuln_case(self, claimed, evidence_uploaded):
        c = _base()
        c["vulnerability_claimed"] = claimed
        c["vulnerability_evidence_uploaded"] = evidence_uploaded
        return c

    # --- WATCH-22.1 ---

    def test_watch_no_vulnerability_claimed_is_pass(self):
        c = self._vuln_case(claimed=False, evidence_uploaded=False)
        r = _watch_22_1(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.1")

    def test_watch_claimed_with_evidence_is_pass(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=True)
        r = _watch_22_1(c)
        self.assertFalse(r.triggered)

    def test_watch_claimed_without_evidence_is_flag(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=False)
        r = _watch_22_1(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "WATCH-22.1")

    def test_watch_message_says_speak_to_tom_or_debra(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=False)
        r = _watch_22_1(c)
        self.assertIn("Tom", r.message)
        self.assertIn("Debra", r.message)

    # --- TIX-06 ---

    def test_tix_no_vulnerability_claimed_is_pass(self):
        c = self._vuln_case(claimed=False, evidence_uploaded=False)
        r = _tix_06(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIX-06")

    def test_tix_claimed_with_evidence_is_pass(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=True)
        r = _tix_06(c)
        self.assertFalse(r.triggered)

    def test_tix_claimed_without_evidence_is_flag(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=False)
        r = _tix_06(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertIn("Tom", r.message)

    # --- EVOLVE-03 ---

    def test_evolve_no_vulnerability_claimed_is_pass(self):
        c = self._vuln_case(claimed=False, evidence_uploaded=False)
        r = _evolve_03(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "EVOLVE-03")

    def test_evolve_claimed_with_evidence_is_pass(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=True)
        r = _evolve_03(c)
        self.assertFalse(r.triggered)

    def test_evolve_claimed_without_evidence_is_flag(self):
        c = self._vuln_case(claimed=True, evidence_uploaded=False)
        r = _evolve_03(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertIn("Debra", r.message)

    # --- Flow-through tests ---

    def test_watch_flows_through_assess_case(self):
        result = _assess(
            detected_reps={"WATCH"},
            vulnerability_claimed=True,
            vulnerability_evidence_uploaded=False,
        )
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("WATCH-22.1", flag_ids)

    def test_tix_flows_through_assess_case(self):
        result = _assess(
            detected_reps={"TIX"},
            vulnerability_claimed=True,
            vulnerability_evidence_uploaded=False,
        )
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("TIX-06", flag_ids)

    def test_evolve_flows_through_assess_case(self):
        result = _assess(
            detected_reps={"EVOLVE"},
            vulnerability_claimed=True,
            vulnerability_evidence_uploaded=False,
        )
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("EVOLVE-03", flag_ids)

    def test_vulnerability_fields_extracted_from_payload(self):
        payload = _minimal_old_payload()
        payload["vulnerability_claimed"] = True
        payload["vulnerability_evidence_uploaded"] = False
        c = _parse_case(payload)
        self.assertTrue(c["vulnerability_claimed"])
        self.assertFalse(c["vulnerability_evidence_uploaded"])

    def test_absent_vulnerability_fields_default_to_false(self):
        c = _base()
        self.assertFalse(c["vulnerability_claimed"])
        self.assertFalse(c["vulnerability_evidence_uploaded"])
