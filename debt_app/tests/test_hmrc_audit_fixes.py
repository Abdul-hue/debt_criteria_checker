"""
Tests verifying the 4 audit fixes applied after the HMRC / gambling audit:

  Fix 1  TIG-15.1   Activated: HMRC majority + income/benefit deduction → hard block
  Fix 2  TIG-15.2   Now also checks previous_iva_failed (bankruptcy coverage)
  Fix 3  TIG-15.10  Now also checks income_is_benefits_only bool (not just income_source string)
  Fix 4  TIG-11-GAMBLING  Separated from TIG-11 so gambling fires even without bank statement
"""

from django.test import TestCase

from debt_app.criteria_engine import (
    _tig_15_1,
    _tig_15_2,
    _tig_15_10,
    _tig_11,
    _tig_11_gambling,
    _parse_case,
    assess_case,
)
from debt_app.tests.test_phase3 import _minimal_old_payload


def _base():
    return _parse_case(_minimal_old_payload())


def _assess(**overrides):
    payload = _minimal_old_payload()
    payload.update(overrides)
    return assess_case(payload)


def _rule_ids(lst):
    return [r.rule_id for r in lst]


def _hmrc_creditor_payload(**overrides):
    """Minimal payload where HMRC is the majority creditor."""
    payload = _minimal_old_payload()
    payload["creditors"] = [
        {"creditor_name": "HMRC", "balance": 15000.00, "creditor_type": "loan"},
        {"creditor_name": "Barclays", "balance": 5000.00, "creditor_type": "loan"},
    ]
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Fix 1: TIG-15.1 — HMRC majority + benefit/income deductions
# ---------------------------------------------------------------------------

class TestTIG151Activation(TestCase):

    def _hmrc_majority_case(self, **extra):
        payload = _hmrc_creditor_payload(**extra)
        return _parse_case(payload)

    def test_no_deductions_is_pass(self):
        c = self._hmrc_majority_case()
        c["income_deductions_active"] = False
        r = _tig_15_1(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-15.1")

    def test_deductions_active_with_hmrc_majority_is_hard_block(self):
        c = self._hmrc_majority_case()
        c["income_deductions_active"] = True
        r = _tig_15_1(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-15.1")

    def test_non_majority_hmrc_never_triggers(self):
        c = _base()
        c["income_deductions_active"] = True
        c["hmrc_is_majority"] = False
        r = _tig_15_1(c)
        self.assertFalse(r.triggered)

    def test_income_deductions_active_extracted_from_payload_top_level(self):
        payload = _hmrc_creditor_payload(income_deductions_active=True)
        c = _parse_case(payload)
        self.assertTrue(c["income_deductions_active"])

    def test_benefit_income_has_deduction_alias_extracted(self):
        payload = _hmrc_creditor_payload(benefit_income_has_deduction=True)
        c = _parse_case(payload)
        self.assertTrue(c["income_deductions_active"])

    def test_flows_through_assess_case(self):
        payload = _hmrc_creditor_payload(income_deductions_active=True)
        result = assess_case(payload)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.1", hard_ids)

    def test_absent_field_is_pass_not_todo_stub(self):
        payload = _hmrc_creditor_payload()
        result = assess_case(payload)
        all_ids = (
            _rule_ids(result["hard_blocks"])
            + _rule_ids(result["flags"])
            + _rule_ids(result["info"])
            + _rule_ids(result["passed"])
        )
        for rid in all_ids:
            self.assertFalse(rid.startswith("TODO-"), msg=f"Unexpected TODO stub: {rid}")


# ---------------------------------------------------------------------------
# Fix 2: TIG-15.2 — previous_iva_failed covers bankruptcy
# ---------------------------------------------------------------------------

class TestTIG152BankruptcyCoverage(TestCase):

    def _hmrc_majority_case(self):
        payload = _hmrc_creditor_payload()
        return _parse_case(payload)

    def test_previous_iva_triggers(self):
        c = self._hmrc_majority_case()
        c["previous_iva"] = True
        c["previous_iva_failed"] = False
        r = _tig_15_2(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")

    def test_previous_iva_failed_triggers(self):
        c = self._hmrc_majority_case()
        c["previous_iva"] = False
        c["previous_iva_failed"] = True
        r = _tig_15_2(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")

    def test_neither_flag_is_pass(self):
        c = self._hmrc_majority_case()
        c["previous_iva"] = False
        c["previous_iva_failed"] = False
        r = _tig_15_2(c)
        self.assertFalse(r.triggered)

    def test_previous_iva_failed_via_client_info(self):
        payload = _hmrc_creditor_payload()
        payload["clientInfo"] = {"previous_iva_failed": True}
        c = _parse_case(payload)
        self.assertTrue(c["previous_iva_failed"])
        r = _tig_15_2(c)
        self.assertTrue(r.triggered)

    def test_flows_through_assess_case_with_iva_failed(self):
        payload = _hmrc_creditor_payload()
        payload["clientInfo"] = {"previous_iva_failed": True}
        result = assess_case(payload)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.2", hard_ids)


# ---------------------------------------------------------------------------
# Fix 3: TIG-15.10 — income_is_benefits_only bool
# ---------------------------------------------------------------------------

class TestTIG1510BenefitsOnlyBool(TestCase):

    def _hmrc_creditor_case(self, **extra):
        c = _base()
        c["hmrc_is_creditor"] = True
        c.update(extra)
        return c

    def test_income_source_benefits_triggers(self):
        c = self._hmrc_creditor_case(income_source="benefits", income_is_benefits_only=False)
        r = _tig_15_10(c)
        self.assertTrue(r.triggered)

    def test_income_source_universal_credit_triggers(self):
        c = self._hmrc_creditor_case(income_source="universal_credit", income_is_benefits_only=False)
        r = _tig_15_10(c)
        self.assertTrue(r.triggered)

    def test_income_is_benefits_only_bool_triggers(self):
        c = self._hmrc_creditor_case(income_source="salary", income_is_benefits_only=True)
        r = _tig_15_10(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-15.10")

    def test_employed_income_and_bool_false_is_pass(self):
        c = self._hmrc_creditor_case(income_source="salary", income_is_benefits_only=False)
        r = _tig_15_10(c)
        self.assertFalse(r.triggered)

    def test_flows_through_assess_case_via_bool(self):
        payload = _hmrc_creditor_payload(income_is_benefits_only=True)
        result = assess_case(payload)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.10", hard_ids)

    def test_no_hmrc_creditor_always_passes(self):
        c = self._hmrc_creditor_case(income_is_benefits_only=True)
        c["hmrc_is_creditor"] = False
        r = _tig_15_10(c)
        self.assertFalse(r.triggered)


# ---------------------------------------------------------------------------
# Fix 4: TIG-11-GAMBLING — fires independently of bank statement
# ---------------------------------------------------------------------------

class TestTIG11GamblingIndependent(TestCase):

    def _case_with_gambling(self, monthly_amount):
        c = _base()
        c["gambling_monthly"] = monthly_amount
        return c

    def test_gambling_above_1000_is_hard_block(self):
        c = self._case_with_gambling(1500)
        r = _tig_11_gambling(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-11-GAMBLING")

    def test_gambling_above_200_below_1000_is_flag(self):
        c = self._case_with_gambling(300)
        r = _tig_11_gambling(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "TIG-11-GAMBLING")

    def test_gambling_below_200_is_pass(self):
        c = self._case_with_gambling(150)
        r = _tig_11_gambling(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "TIG-11-GAMBLING")

    def test_gambling_fires_when_no_bank_statement(self):
        """Critical: gambling hard block must appear even when bank statement is missing."""
        payload = _minimal_old_payload()
        payload["gold_transactions"] = [
            {"description": "betfair payment", "amount": -600, "date": "2026-04-10"},
            {"description": "paddy power bet", "amount": -600, "date": "2026-04-15"},
        ]
        # No bank statement docs — TIG-11 fires for missing statement,
        # TIG-11-GAMBLING should ALSO fire independently for gambling
        payload.pop("documents", None)
        result = assess_case(payload)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-11", hard_ids)
        self.assertIn("TIG-11-GAMBLING", hard_ids)

    def test_tig_11_no_longer_returns_gambling_rule_id(self):
        """TIG-11 now only covers bank statement — gambling is TIG-11-GAMBLING."""
        c = self._case_with_gambling(5000)
        c["bank_stmt_docs"] = [{"type": "bank_statement"}]
        c["bank_stmt_date"] = "2026-04-01"  # within 90 days of 2026-05-16
        c["bank_stmt_holder"] = "Test User"
        r = _tig_11(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-11")

    def test_flows_through_assess_case_hard_block(self):
        payload = _minimal_old_payload()
        # gold_transactions uses 'description' field, not 'merchant'
        payload["gold_transactions"] = [
            {"description": "betfair payment", "amount": -600, "date": "2026-04-10"},
            {"description": "betfair payment", "amount": -600, "date": "2026-04-15"},
        ]
        result = assess_case(payload)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-11-GAMBLING", hard_ids)

    def test_flows_through_assess_case_flag(self):
        payload = _minimal_old_payload()
        payload["gold_transactions"] = [
            {"description": "betfair payment", "amount": -150, "date": "2026-04-10"},
            {"description": "paddy power", "amount": -100, "date": "2026-04-15"},
        ]
        result = assess_case(payload)
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("TIG-11-GAMBLING", flag_ids)
