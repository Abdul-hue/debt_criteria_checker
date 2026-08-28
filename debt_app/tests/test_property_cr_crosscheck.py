"""
Property / mortgage data cross-check regression tests.

Motivated by Theresa Topp case 324991: Aryza property tables were empty,
but her credit report showed an active Lloyds mortgage (£106,098 outstanding,
in arrears). The engine read has_property=False and every equity rule silently
passed as "not applicable". This file verifies the fix.

Covers _cross_check_property_from_credit_report() for three cases:

  Case 1 – Aryza property tables empty, credit report has mortgage account.
  Case 2 – Aryza has property data (regression guard — no change expected).
  Case 3 – Both sources present but disagree by > £50 (conflict).
"""

from django.test import SimpleTestCase

from debt_app.engine.criteria import _cross_check_property_from_credit_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_case_no_property():
    """Case dict as _parse_case emits it when Aryza property tables are empty."""
    return {
        "has_property": False,
        "property_value": None,
        "mortgage_balance": 0.0,
        "available_equity": 0.0,
    }


def _base_case_with_property(pv=200_000.0, mb=106_098.0):
    """Case dict with Aryza property data populated."""
    return {
        "has_property": True,
        "property_value": pv,
        "mortgage_balance": mb,
        "available_equity": pv - mb,
    }


def _lloyds_mortgage_account(balance_pence=10_609_800):
    """
    Minimal credit report mortgage account dict as integrations/credit_report.py emits it.
    Default balance: 10,609,800 pence = £106,098.00 (Theresa Topp's actual balance).
    """
    return {
        "raw_name": "Lloyds Bank Mortgages Ltd",
        "type_code": "MG",
        "normalised_name": "lloyds bank mortgages ltd",
        "matched_creditor": "Lloyds Bank Mortgages Ltd",
        "account_status": "late",           # in arrears
        "current_balance": balance_pence,   # pence
        "missed_payments_last_3_months": 3,
        "monthly_payment": None,
        "account_age_months": 120,
        "payment_history_months": 120,
        "recent_spending": False,
        "credit_limit": None,
        "utilisation_pct": None,
    }


def _cr_data(balance_pence=10_609_800):
    return {"mortgage_accounts": [_lloyds_mortgage_account(balance_pence)]}


def _cr_data_empty():
    return {"mortgage_accounts": []}


def _closed_mortgage_account(balance_pence=0):
    """Fully repaid/settled mortgage as the extractor would emit it."""
    return {
        "raw_name": "Nationwide Building Society",
        "type_code": "MG",
        "normalised_name": "nationwide building society",
        "matched_creditor": "Nationwide Building Society",
        "account_status": "closed",
        "current_balance": balance_pence,
        "missed_payments_last_3_months": 0,
        "monthly_payment": None,
        "account_age_months": 240,
        "payment_history_months": 240,
        "recent_spending": False,
        "credit_limit": None,
        "utilisation_pct": None,
    }


def _cr_data_closed_only(balance_pence=0):
    return {"mortgage_accounts": [_closed_mortgage_account(balance_pence)]}


# ---------------------------------------------------------------------------
# Case 1: Aryza empty, credit report has mortgage
# ---------------------------------------------------------------------------

class Case1AryazaEmptyTests(SimpleTestCase):
    """
    Theresa Topp scenario: Aryza slam_property/mortgage tables empty,
    credit report shows active Lloyds mortgage in arrears.
    """

    def setUp(self):
        self.c = _base_case_no_property()
        self.findings = _cross_check_property_from_credit_report(self.c, _cr_data())

    def test_has_property_becomes_true(self):
        # A mortgage account implies property ownership
        self.assertTrue(self.c["has_property"])

    def test_mortgage_balance_set_from_credit_report(self):
        # 10,609,800 pence ÷ 100 = £106,098.00
        self.assertAlmostEqual(self.c["mortgage_balance"], 106_098.0, places=0)

    def test_property_value_remains_none(self):
        # Credit reports contain no property valuation signal — only the mortgage debt
        self.assertIsNone(self.c["property_value"])

    def test_available_equity_is_none(self):
        # has_property=True + property_value=None → None
        # (triggers existing [RULE-CANNOT-EVALUATE] path in every equity rule)
        self.assertIsNone(self.c["available_equity"])

    def test_property_data_source_tagged(self):
        self.assertEqual(self.c["property_data_source"], "credit_report_fallback")

    def test_flag_emitted(self):
        rule_ids = [f.rule_id for f in self.findings]
        self.assertIn("PROPERTY-DATA-FROM-CREDIT-REPORT", rule_ids)

    def test_flag_severity_is_flag(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-FROM-CREDIT-REPORT")
        self.assertEqual(flag.severity, "flag")

    def test_flag_triggered_true(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-FROM-CREDIT-REPORT")
        self.assertTrue(flag.triggered)

    def test_flag_message_contains_balance(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-FROM-CREDIT-REPORT")
        self.assertIn("106,098.00", flag.message)

    def test_flag_message_mentions_aryza_empty(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-FROM-CREDIT-REPORT")
        self.assertIn("case file", flag.message)

    def test_flag_message_mentions_lender(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-FROM-CREDIT-REPORT")
        self.assertIn("Lloyds", flag.message)

    def test_exactly_one_finding(self):
        self.assertEqual(len(self.findings), 1)


class Case1NoCreditReportMortgageTests(SimpleTestCase):
    """No credit report mortgage accounts → function is a no-op."""

    def test_no_findings_when_cr_has_no_mortgage(self):
        c = _base_case_no_property()
        findings = _cross_check_property_from_credit_report(c, _cr_data_empty())
        self.assertEqual(findings, [])

    def test_case_dict_unchanged_when_cr_empty(self):
        c = _base_case_no_property()
        _cross_check_property_from_credit_report(c, _cr_data_empty())
        self.assertFalse(c["has_property"])
        self.assertIsNone(c["property_value"])
        self.assertEqual(c["mortgage_balance"], 0.0)

    def test_no_findings_when_cr_data_missing_key(self):
        # credit_report_data may not have mortgage_accounts key at all
        c = _base_case_no_property()
        findings = _cross_check_property_from_credit_report(c, {})
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Case 2: Aryza populated — regression guard
# ---------------------------------------------------------------------------

class Case2AryazaPopulatedNoConflictTests(SimpleTestCase):
    """
    Regression guard: cases where Aryza already has property data must be
    entirely unaffected when the credit report agrees (diff ≤ £50).
    """

    def setUp(self):
        # Aryza mb = £106,098; credit report also £106,098 → diff = 0
        self.c = _base_case_with_property(pv=200_000.0, mb=106_098.0)
        self.findings = _cross_check_property_from_credit_report(self.c, _cr_data(10_609_800))

    def test_no_flags_emitted(self):
        self.assertEqual(self.findings, [])

    def test_has_property_unchanged(self):
        self.assertTrue(self.c["has_property"])

    def test_property_value_unchanged(self):
        self.assertEqual(self.c["property_value"], 200_000.0)

    def test_mortgage_balance_unchanged(self):
        self.assertAlmostEqual(self.c["mortgage_balance"], 106_098.0, places=0)

    def test_available_equity_unchanged(self):
        self.assertAlmostEqual(self.c["available_equity"], 200_000.0 - 106_098.0, places=0)


class Case2AryazaPopulatedNoCRMortgageTests(SimpleTestCase):
    """Aryza has data; credit report has no mortgage section at all."""

    def test_no_flags_when_no_cr_mortgage(self):
        c = _base_case_with_property()
        findings = _cross_check_property_from_credit_report(c, _cr_data_empty())
        self.assertEqual(findings, [])

    def test_case_dict_unchanged(self):
        c = _base_case_with_property(pv=180_000.0, mb=90_000.0)
        _cross_check_property_from_credit_report(c, _cr_data_empty())
        self.assertTrue(c["has_property"])
        self.assertEqual(c["property_value"], 180_000.0)
        self.assertEqual(c["mortgage_balance"], 90_000.0)


# ---------------------------------------------------------------------------
# Case 3: Conflicting values (diff > £50)
# ---------------------------------------------------------------------------

class Case3ConflictTests(SimpleTestCase):
    """
    Both Aryza and credit report have mortgage data but disagree by > £50.
    Spec decision: use higher balance conservatively.
    """

    def setUp(self):
        # Aryza says £80,000; credit report says £106,098 — diff = £26,098 > £50
        self.c = _base_case_with_property(pv=200_000.0, mb=80_000.0)
        self.findings = _cross_check_property_from_credit_report(self.c, _cr_data(10_609_800))

    def test_conflict_flag_emitted(self):
        rule_ids = [f.rule_id for f in self.findings]
        self.assertIn("PROPERTY-DATA-CONFLICT", rule_ids)

    def test_flag_severity_is_flag(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertEqual(flag.severity, "flag")

    def test_higher_balance_used(self):
        # CR £106,098 > Aryza £80,000 → use £106,098
        self.assertAlmostEqual(self.c["mortgage_balance"], 106_098.0, places=0)

    def test_flag_message_contains_aryza_balance(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertIn("80,000.00", flag.message)

    def test_flag_message_contains_cr_balance(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertIn("106,098.00", flag.message)

    def test_flag_message_mentions_aryza_source(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertIn("case file", flag.message)

    def test_flag_message_mentions_cr_source(self):
        flag = next(f for f in self.findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertIn("credit report", flag.message)

    def test_available_equity_recomputed_with_higher_balance(self):
        # pv=£200,000, new mb=£106,098 → equity = £93,902
        self.assertAlmostEqual(self.c["available_equity"], 200_000.0 - 106_098.0, places=0)

    def test_aryza_higher_wins_when_aryza_is_larger(self):
        # Aryza £120,000; CR £106,098 — diff = £13,902 > £50 → use Aryza's £120,000
        c = _base_case_with_property(pv=200_000.0, mb=120_000.0)
        findings = _cross_check_property_from_credit_report(c, _cr_data(10_609_800))
        self.assertAlmostEqual(c["mortgage_balance"], 120_000.0, places=0)
        flag = next(f for f in findings if f.rule_id == "PROPERTY-DATA-CONFLICT")
        self.assertIn("case file", flag.message)

    def test_no_conflict_when_diff_at_or_below_50(self):
        # Aryza £106,048; CR £106,098 — diff = £50 → NOT a conflict (boundary)
        c = _base_case_with_property(pv=200_000.0, mb=106_048.0)
        findings = _cross_check_property_from_credit_report(c, _cr_data(10_609_800))
        conflict = [f for f in findings if f.rule_id == "PROPERTY-DATA-CONFLICT"]
        self.assertEqual(conflict, [])


# ---------------------------------------------------------------------------
# Closed / settled mortgage — must NOT produce a false has_property=True
# ---------------------------------------------------------------------------

class ClosedMortgageTests(SimpleTestCase):
    """
    A closed (fully repaid) mortgage means the debt is gone. The client may
    have sold the property or fully repaid. We cannot safely infer has_property.
    Pre-fix, any non-empty mortgage_accounts[] list would trigger Case 1 and
    emit a spurious has_property=True with mortgage_balance=£0.00.
    """

    def test_closed_zero_balance_produces_no_findings(self):
        c = _base_case_no_property()
        findings = _cross_check_property_from_credit_report(c, _cr_data_closed_only(0))
        self.assertEqual(findings, [])

    def test_closed_zero_balance_leaves_has_property_false(self):
        c = _base_case_no_property()
        _cross_check_property_from_credit_report(c, _cr_data_closed_only(0))
        self.assertFalse(c["has_property"])

    def test_closed_with_residual_pence_produces_no_findings(self):
        # Extraction artefact: status="closed" but tiny residual in balance field
        c = _base_case_no_property()
        findings = _cross_check_property_from_credit_report(c, _cr_data_closed_only(50))
        self.assertEqual(findings, [])

    def test_closed_leaves_mortgage_balance_at_zero(self):
        c = _base_case_no_property()
        _cross_check_property_from_credit_report(c, _cr_data_closed_only(0))
        self.assertEqual(c["mortgage_balance"], 0.0)

    def test_active_plus_closed_only_counts_active(self):
        # One active Lloyds (£106,098) + one closed Nationwide (£0)
        # Only the active one should count; closed is ignored.
        cr_data = {
            "mortgage_accounts": [
                _lloyds_mortgage_account(10_609_800),    # active, late
                _closed_mortgage_account(0),              # closed, zero
            ]
        }
        c = _base_case_no_property()
        findings = _cross_check_property_from_credit_report(c, cr_data)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn("PROPERTY-DATA-FROM-CREDIT-REPORT", rule_ids)
        # Balance should reflect only the active account
        self.assertAlmostEqual(c["mortgage_balance"], 106_098.0, places=0)
