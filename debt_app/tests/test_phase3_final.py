"""
Phase 3 Final Core Rules — tests.

Covers:
  TIG-15.5  bankruptcy_return vs IVA return
  TIG-15.6  full_and_final_from_savings hard block
  TIG-15.7  SEISS fraud debt hard block
  WATCH-22.3  bankruptcy_return vs WATCH IVA return
  WATCH-22.7  children aged 13+ / sustainability paragraph
  WATCH-22.9  vehicle value > £9,000
  WATCH-22.11 gambling as main cause of debt
  WATCH-22.13 antecedent transactions hard block
"""

from django.test import TestCase

from debt_app.criteria_engine import (
    _tig_15_5,
    _tig_15_6,
    _tig_15_7,
    _watch_22_3,
    _watch_22_7,
    _watch_22_9,
    _watch_22_11,
    _watch_22_13,
    _parse_case,
    assess_case,
    NON_OVERRIDABLE_RULE_IDS,
)
from debt_app.tests.test_phase3 import _minimal_old_payload


def _base():
    """Minimal parsed case dict: all new fields absent / falsy."""
    payload = _minimal_old_payload()
    return _parse_case(payload)


def _assess(detected_reps=None, **overrides):
    payload = _minimal_old_payload()
    payload.update(overrides)
    return assess_case(payload, detected_representatives=detected_reps)


def _rule_ids(results):
    return [r.rule_id for r in results]


# ---------------------------------------------------------------------------
# TIG-15.5: bankruptcy_return > IVA return
# ---------------------------------------------------------------------------

class TestTIG155(TestCase):

    def test_bankruptcy_return_none_is_pass(self):
        c = _base()
        c["bankruptcy_return"] = None
        r = _tig_15_5(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-15.5")

    def test_bankruptcy_exceeds_iva_return_is_hard_block(self):
        c = _base()
        # DI = 200/month; IVA return = 200 * 60 * 0.75 = 9000
        c["disposable_income"] = 200.0
        c["bankruptcy_return"] = 10000.0
        r = _tig_15_5(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-15.5")

    def test_iva_exceeds_bankruptcy_return_is_pass(self):
        c = _base()
        c["disposable_income"] = 200.0
        c["bankruptcy_return"] = 5000.0  # less than 9000
        r = _tig_15_5(c)
        self.assertFalse(r.triggered)

    def test_flows_through_assess_case(self):
        result = _assess(bankruptcy_return=99999.0)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.5", hard_ids)


# ---------------------------------------------------------------------------
# TIG-15.6: full_and_final_from_savings
# ---------------------------------------------------------------------------

class TestTIG156(TestCase):

    def test_flag_absent_is_pass(self):
        c = _base()
        r = _tig_15_6(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-15.6")

    def test_flag_false_is_pass(self):
        c = _base()
        c["full_and_final_from_savings"] = False
        r = _tig_15_6(c)
        self.assertFalse(r.triggered)

    def test_flag_true_is_hard_block(self):
        c = _base()
        c["full_and_final_from_savings"] = True
        r = _tig_15_6(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-15.6")

    def test_flows_through_assess_case(self):
        result = _assess(full_and_final_from_savings=True)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.6", hard_ids)


# ---------------------------------------------------------------------------
# TIG-15.7: SEISS fraud debt
# ---------------------------------------------------------------------------

class TestTIG157(TestCase):

    def test_seiss_flag_none_is_pass(self):
        c = _base()
        c["seiss_debt_flag"] = None
        r = _tig_15_7(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "TIG-15.7")

    def test_seiss_flag_false_is_pass(self):
        c = _base()
        c["seiss_debt_flag"] = False
        r = _tig_15_7(c)
        self.assertFalse(r.triggered)

    def test_seiss_flag_true_is_hard_block(self):
        c = _base()
        c["seiss_debt_flag"] = True
        r = _tig_15_7(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "TIG-15.7")

    def test_flows_through_assess_case(self):
        result = _assess(seiss_debt_flag=True)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("TIG-15.7", hard_ids)


# ---------------------------------------------------------------------------
# WATCH-22.3: bankruptcy_return vs WATCH IVA return
# ---------------------------------------------------------------------------

class TestWATCH223(TestCase):

    def test_none_is_pass(self):
        c = _base()
        c["bankruptcy_return"] = None
        r = _watch_22_3(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.3")

    def test_bankruptcy_exceeds_iva_is_hard_block(self):
        c = _base()
        c["disposable_income"] = 200.0
        c["bankruptcy_return"] = 10000.0
        r = _watch_22_3(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")

    def test_iva_exceeds_bankruptcy_is_pass(self):
        c = _base()
        c["disposable_income"] = 200.0
        c["bankruptcy_return"] = 5000.0
        r = _watch_22_3(c)
        self.assertFalse(r.triggered)


# ---------------------------------------------------------------------------
# WATCH-22.7: children aged 13+
# ---------------------------------------------------------------------------

class TestWATCH227(TestCase):

    def test_no_children_is_pass(self):
        c = _base()
        c["children"] = []
        r = _watch_22_7(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.7")

    def test_children_field_absent_is_pass(self):
        c = _base()
        r = _watch_22_7(c)
        self.assertFalse(r.triggered)

    def test_child_under_13_is_pass(self):
        c = _base()
        c["children"] = [{"age": 12}]
        r = _watch_22_7(c)
        self.assertFalse(r.triggered)

    def test_child_13_no_sustainability_is_flag(self):
        c = _base()
        c["children"] = [{"age": 13}]
        c["sustainability_paragraph_present"] = False
        r = _watch_22_7(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "WATCH-22.7")

    def test_child_13_with_sustainability_is_pass(self):
        c = _base()
        c["children"] = [{"age": 13}]
        c["sustainability_paragraph_present"] = True
        r = _watch_22_7(c)
        self.assertFalse(r.triggered)

    def test_mixed_children_teen_triggers_flag(self):
        c = _base()
        c["children"] = [{"age": 8}, {"age": 15}]
        c["sustainability_paragraph_present"] = False
        r = _watch_22_7(c)
        self.assertTrue(r.triggered)

    def test_flows_through_assess_case_flag(self):
        result = _assess(
            detected_reps={"WATCH"},
            children=[{"age": 14}],
            sustainability_paragraph_present=False,
        )
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("WATCH-22.7", flag_ids)

    def test_flows_through_assess_case_no_flag_with_paragraph(self):
        result = _assess(
            detected_reps={"WATCH"},
            children=[{"age": 14}],
            sustainability_paragraph_present=True,
        )
        flag_ids = _rule_ids(result["flags"])
        self.assertNotIn("WATCH-22.7", flag_ids)


# ---------------------------------------------------------------------------
# WATCH-22.9: vehicle value > £9,000
# ---------------------------------------------------------------------------

class TestWATCH229(TestCase):

    def test_no_vehicle_value_is_pass(self):
        c = _base()
        c["vehicle_value"] = None
        r = _watch_22_9(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.9")

    def test_vehicle_value_below_threshold_is_pass(self):
        c = _base()
        c["vehicle_value"] = 8000.0
        r = _watch_22_9(c)
        self.assertFalse(r.triggered)

    def test_vehicle_value_above_threshold_is_flag(self):
        c = _base()
        c["vehicle_value"] = 10000.0
        r = _watch_22_9(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "WATCH-22.9")

    def test_vehicle_value_exactly_threshold_is_pass(self):
        c = _base()
        c["vehicle_value"] = 9000.0
        r = _watch_22_9(c)
        self.assertFalse(r.triggered)

    def test_message_mentions_downgrade(self):
        c = _base()
        c["vehicle_value"] = 12000.0
        r = _watch_22_9(c)
        self.assertIn("4,500", r.message)

    def test_flows_through_assess_case_flag(self):
        result = _assess(detected_reps={"WATCH"}, vehicle_value=15000.0)
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("WATCH-22.9", flag_ids)

    def test_flows_through_assess_case_no_flag(self):
        result = _assess(detected_reps={"WATCH"}, vehicle_value=7000.0)
        flag_ids = _rule_ids(result["flags"])
        self.assertNotIn("WATCH-22.9", flag_ids)


# ---------------------------------------------------------------------------
# WATCH-22.11: gambling as main cause
# ---------------------------------------------------------------------------

class TestWATCH2211(TestCase):

    def test_gambling_main_cause_false_is_pass(self):
        c = _base()
        c["gambling_main_cause"] = False
        r = _watch_22_11(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.11")

    def test_gambling_main_cause_absent_is_pass(self):
        c = _base()
        r = _watch_22_11(c)
        self.assertFalse(r.triggered)

    def test_gambling_main_cause_true_is_flag(self):
        c = _base()
        c["gambling_main_cause"] = True
        r = _watch_22_11(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "flag")
        self.assertEqual(r.rule_id, "WATCH-22.11")

    def test_flows_through_assess_case(self):
        result = _assess(detected_reps={"WATCH"}, gambling_main_cause=True)
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("WATCH-22.11", flag_ids)

    def test_gambling_monthly_without_main_cause_does_not_trigger(self):
        """High gambling_monthly alone no longer triggers WATCH-22.11 (TIG-11 handles that)."""
        payload = _minimal_old_payload()
        payload["transactions"] = [
            {"merchant": "Betfair", "amount": -500, "date": "2025-01-10"},
            {"merchant": "Paddy Power", "amount": -300, "date": "2025-01-15"},
        ]
        payload["gambling_main_cause"] = False
        result = assess_case(payload)
        flag_ids = _rule_ids(result["flags"])
        self.assertNotIn("WATCH-22.11", flag_ids)

    def test_crm_data_gambling_main_cause_is_read(self):
        """gambling_main_cause inside crm_data is also picked up."""
        payload = _minimal_old_payload()
        payload["crm_data"]["gambling_main_cause"] = True
        c = _parse_case(payload)
        self.assertTrue(c["gambling_main_cause"])


# ---------------------------------------------------------------------------
# WATCH-22.13: antecedent transactions
# ---------------------------------------------------------------------------

class TestWATCH2213(TestCase):

    def test_in_non_overridable_rule_ids(self):
        self.assertIn("WATCH-22.13", NON_OVERRIDABLE_RULE_IDS)

    def test_antecedent_transactions_none_is_pass(self):
        c = _base()
        c["antecedent_transactions"] = None
        r = _watch_22_13(c)
        self.assertFalse(r.triggered)
        self.assertEqual(r.rule_id, "WATCH-22.13")

    def test_antecedent_transactions_false_is_pass(self):
        c = _base()
        c["antecedent_transactions"] = False
        r = _watch_22_13(c)
        self.assertFalse(r.triggered)

    def test_antecedent_transactions_true_is_hard_block(self):
        c = _base()
        c["antecedent_transactions"] = True
        r = _watch_22_13(c)
        self.assertTrue(r.triggered)
        self.assertEqual(r.severity, "hard_block")
        self.assertEqual(r.rule_id, "WATCH-22.13")

    def test_flows_through_assess_case(self):
        result = _assess(detected_reps={"WATCH"}, antecedent_transactions=True)
        hard_ids = _rule_ids(result["hard_blocks"])
        self.assertIn("WATCH-22.13", hard_ids)

    def test_absent_field_no_longer_returns_todo_stub(self):
        payload = _minimal_old_payload()
        payload.pop("antecedent_transactions", None)
        result = assess_case(payload)
        all_rule_ids = (
            _rule_ids(result["hard_blocks"])
            + _rule_ids(result["flags"])
            + _rule_ids(result["info"])
            + _rule_ids(result["passed"])
        )
        for rid in all_rule_ids:
            self.assertFalse(
                rid.startswith("TODO-"),
                msg=f"Unexpected TODO stub in results: {rid}",
            )
