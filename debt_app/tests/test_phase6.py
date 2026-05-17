"""
Phase 6 engine tests: special employer, I&E match, repayability, guarantor, conditional voters.

Includes unit tests (individual functions) and integration tests (full assess_case pipeline
through build_phase7_response_fields — the ResultAggregator).
"""

from django.test import TestCase

from debt_app.criteria_engine import (
    _check_conditional_voters,
    _check_debt_repayability,
    _check_guarantor_rules,
    _check_ie_match,
    _check_special_employer,
    _parse_case,
    assess_case,
)
from debt_app.models import (
    ConditionalVoterRule,
    CreditorCriteria,
    CreditorOpenBankingRule,
)
from debt_app.tests.test_phase4 import _phase4_base_payload
from debt_app.views.criteria_views import build_phase7_response_fields


def _phase6_payload(**overrides):
    payload = _phase4_base_payload()
    payload.update(overrides)
    return payload


def _parsed(**overrides):
    return _parse_case(_phase6_payload(**overrides))


def _rule_ids(results):
    return [r.rule_id for r in results]


class TestSpecialEmployer(TestCase):
    def test_royal_mail_penny_post_info(self):
        case = _parsed(
            is_royal_mail_employee=True,
            creditors=[
                {
                    "creditor_name": "Penny Post CU",
                    "balance": 2000.0,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_special_employer(case)
        self.assertIn("SPECIAL-EMPLOYER-PENNY-POST", _rule_ids(results))

    def test_royal_mail_no_penny_post_no_result(self):
        case = _parsed(
            is_royal_mail_employee=True,
            creditors=[
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_special_employer(case)
        self.assertEqual(_rule_ids(results), [])

    def test_police_copperpot_hard_block(self):
        case = _parsed(
            is_police_officer=True,
            creditors=[
                {
                    "creditor_name": "No1 Copperpot CU",
                    "balance": 1500.0,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_special_employer(case)
        self.assertIn("SPECIAL-EMPLOYER-COPPERPOT", _rule_ids(results))
        block = next(r for r in results if r.rule_id == "SPECIAL-EMPLOYER-COPPERPOT")
        self.assertEqual(block.severity, "hard_block")

    def test_police_no_copperpot_no_result(self):
        case = _parsed(
            is_police_officer=True,
            creditors=[
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_special_employer(case)
        self.assertEqual(_rule_ids(results), [])


class TestIeMatch(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.bamboo = CreditorCriteria.objects.filter(
            creditor_name__icontains="Bamboo"
        ).first()

    def test_ie_must_match_false_blocks(self):
        self.assertIsNotNone(self.bamboo)
        CreditorOpenBankingRule.objects.update_or_create(
            creditor=self.bamboo,
            defaults={"ie_must_match_exactly": True, "review_period_months": 3},
        )
        case = _parsed(
            creditors=[
                {
                    "creditor_name": "Bamboo",
                    "balance": 3000.0,
                    "creditor_type": "loan",
                    "ie_matches_loan_application": False,
                },
            ],
        )
        results = _check_ie_match(case)
        self.assertIn("IE-MATCH-FAIL", _rule_ids(results))

    def test_ie_must_match_true_no_block(self):
        self.assertIsNotNone(self.bamboo)
        CreditorOpenBankingRule.objects.update_or_create(
            creditor=self.bamboo,
            defaults={"ie_must_match_exactly": True, "review_period_months": 3},
        )
        case = _parsed(
            creditors=[
                {
                    "creditor_name": "Bamboo",
                    "balance": 3000.0,
                    "creditor_type": "loan",
                    "ie_matches_loan_application": True,
                },
            ],
        )
        results = _check_ie_match(case)
        self.assertNotIn("IE-MATCH-FAIL", _rule_ids(results))

    def test_no_open_banking_rule_no_block(self):
        case = _parsed(
            creditors=[
                {
                    "creditor_name": "Totally Unknown Lender XYZ",
                    "balance": 1000.0,
                    "creditor_type": "loan",
                    "ie_matches_loan_application": False,
                },
            ],
        )
        results = _check_ie_match(case)
        self.assertEqual(_rule_ids(results), [])


class TestDebtRepayability(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cambrian = CreditorCriteria.objects.filter(
            creditor_name__icontains="CAMBRIAN"
        ).first()

    def test_repayable_within_threshold_blocks(self):
        self.assertIsNotNone(self.cambrian)
        self.assertEqual(self.cambrian.reject_if_debt_repayable_within_months, 6)
        case = _parsed(
            monthly_di=1500.0,
            creditors=[
                {
                    "creditor_name": "CAMBRIAN Credit Union",
                    "balance": 6000.0,
                    "crm_balance": 6000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_debt_repayability(case)
        self.assertIn("DEBT-REPAYABILITY-REJECT", _rule_ids(results))

    def test_repayable_outside_threshold_no_block(self):
        self.assertIsNotNone(self.cambrian)
        case = _parsed(
            monthly_di=500.0,
            creditors=[
                {
                    "creditor_name": "CAMBRIAN Credit Union",
                    "balance": 6000.0,
                    "crm_balance": 6000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_debt_repayability(case)
        self.assertNotIn("DEBT-REPAYABILITY-REJECT", _rule_ids(results))

    def test_zero_di_no_block(self):
        self.assertIsNotNone(self.cambrian)
        case = _parsed(
            monthly_di=0.0,
            creditors=[
                {
                    "creditor_name": "CAMBRIAN Credit Union",
                    "balance": 6000.0,
                    "crm_balance": 6000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        results = _check_debt_repayability(case)
        self.assertEqual(_rule_ids(results), [])


class TestGuarantorRules(TestCase):
    def test_pg_not_called_up_flags(self):
        creditor = CreditorCriteria.objects.filter(
            creditor_name__icontains="Barclays"
        ).first()
        if creditor is None:
            creditor = CreditorCriteria.objects.filter(is_active=True).first()
        self.assertIsNotNone(creditor)
        creditor.requires_pg_called_up = True
        creditor.save(update_fields=["requires_pg_called_up"])
        case = _parsed(
            creditors=[
                {
                    "creditor_name": creditor.creditor_name,
                    "balance": 5000.0,
                    "creditor_type": "loan",
                    "guarantee_called_up": False,
                },
            ],
        )
        results = _check_guarantor_rules(case)
        self.assertIn("GUARANTOR-NOT-CALLED-UP", _rule_ids(results))
        creditor.requires_pg_called_up = False
        creditor.save(update_fields=["requires_pg_called_up"])

    def test_pg_called_up_no_flag(self):
        creditor = CreditorCriteria.objects.filter(
            creditor_name__icontains="Barclays"
        ).first()
        if creditor is None:
            creditor = CreditorCriteria.objects.filter(is_active=True).first()
        self.assertIsNotNone(creditor)
        creditor.requires_pg_called_up = True
        creditor.save(update_fields=["requires_pg_called_up"])
        case = _parsed(
            creditors=[
                {
                    "creditor_name": creditor.creditor_name,
                    "balance": 5000.0,
                    "creditor_type": "loan",
                    "guarantee_called_up": True,
                },
            ],
        )
        results = _check_guarantor_rules(case)
        self.assertNotIn("GUARANTOR-NOT-CALLED-UP", _rule_ids(results))
        creditor.requires_pg_called_up = False
        creditor.save(update_fields=["requires_pg_called_up"])


class TestConditionalVoters(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buddy = CreditorCriteria.objects.filter(
            creditor_name__icontains="Buddy"
        ).first()
        cls.salary = CreditorCriteria.objects.filter(
            creditor_name__icontains="Salary Finance"
        ).first()

    def _case_with_balances(self, **overrides):
        defaults = {
            "monthly_di": 200.0,
            "creditors": [
                {
                    "creditor_name": "Barclays",
                    "balance": 9000.0,
                    "crm_balance": 9000.0,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Buddy Loans",
                    "balance": 1000.0,
                    "crm_balance": 1000.0,
                    "creditor_type": "loan",
                },
            ],
        }
        defaults.update(overrides)
        return _parsed(**defaults)

    def test_majority_achievable_not_needed(self):
        self.assertIsNotNone(self.buddy)
        case = self._case_with_balances()
        positions = [
            {
                "creditor_name": "Barclays",
                "effective_status": "ACCEPT",
            },
            {
                "creditor_name": "Buddy Loans",
                "effective_status": "CONDITIONAL_VOTER",
            },
        ]
        results = _check_conditional_voters(case, positions)
        self.assertIn("CONDITIONAL-VOTER-NOT-NEEDED", _rule_ids(results))
        self.assertNotIn("CONDITIONAL-VOTER-REQUIRED", _rule_ids(results))

    def test_majority_not_achievable_contact_required(self):
        self.assertIsNotNone(self.salary)
        case = _parsed(
            monthly_di=200.0,
            creditors=[
                {
                    "creditor_name": "Barclays",
                    "balance": 2000.0,
                    "crm_balance": 2000.0,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Salary Finance",
                    "balance": 8000.0,
                    "crm_balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = [
            {"creditor_name": "Barclays", "effective_status": "ACCEPT"},
            {"creditor_name": "Salary Finance", "effective_status": "CONDITIONAL_VOTER"},
        ]
        cv = ConditionalVoterRule.objects.get(creditor=self.salary)
        self.assertTrue(cv.contact_required)
        results = _check_conditional_voters(case, positions)
        ids = _rule_ids(results)
        self.assertIn("CONDITIONAL-VOTER-REQUIRED", ids)
        self.assertIn("CONDITIONAL-VOTER-CONTACT-REQUIRED", ids)
        self.assertNotIn("CONDITIONAL-VOTER-NOT-NEEDED", ids)


# ---------------------------------------------------------------------------
# Integration tests — full assess_case() → build_phase7_response_fields pipeline
# (ResultAggregator coverage)
# ---------------------------------------------------------------------------

def _m6_payload(**overrides):
    """Minimal payload that passes TIG-01/02 and is otherwise clean for Module 6 testing."""
    payload = _phase4_base_payload()
    payload.update(overrides)
    return payload


class TestModule6Integration(TestCase):
    """
    End-to-end: Module 6 findings must flow through assess_case() into the
    serialized response produced by build_phase7_response_fields (ResultAggregator).
    """

    def _ids_in_bin(self, serialized, bin_name):
        return [r["rule_id"] for r in serialized.get(bin_name, [])]

    def test_copperpot_hard_block_in_assess_case_response(self):
        """SPECIAL-EMPLOYER-COPPERPOT must appear in hard_blocks of the full response."""
        result = assess_case(
            _m6_payload(
                is_police_officer=True,
                creditors=[
                    {"creditor_name": "No1 Copperpot CU", "balance": 1500.0, "creditor_type": "loan"},
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        self.assertIn(
            "SPECIAL-EMPLOYER-COPPERPOT",
            [r.rule_id for r in result["hard_blocks"]],
        )
        self.assertEqual(result["overall"], "blocked")
        self.assertFalse(result["passes_all_hard_blocks"])

    def test_penny_post_info_in_assess_case_response(self):
        """SPECIAL-EMPLOYER-PENNY-POST must appear in info of the full response."""
        result = assess_case(
            _m6_payload(
                is_royal_mail_employee=True,
                creditors=[
                    {"creditor_name": "Penny Post CU", "balance": 2000.0, "creditor_type": "loan"},
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        self.assertIn(
            "SPECIAL-EMPLOYER-PENNY-POST",
            [r.rule_id for r in result["info"]],
        )

    def test_debt_repayability_hard_block_in_assess_case_response(self):
        """DEBT-REPAYABILITY-REJECT must appear in hard_blocks when balance/DI < threshold."""
        result = assess_case(
            _m6_payload(
                monthly_di=1500.0,
                creditors=[
                    {"creditor_name": "CAMBRIAN Credit Union", "balance": 6000.0, "creditor_type": "loan"},
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        self.assertIn(
            "DEBT-REPAYABILITY-REJECT",
            [r.rule_id for r in result["hard_blocks"]],
        )

    def test_guarantor_flag_in_assess_case_response(self):
        """GUARANTOR-NOT-CALLED-UP must appear in flags when PG not called up."""
        creditor = CreditorCriteria.objects.filter(is_active=True).first()
        self.assertIsNotNone(creditor)
        creditor.requires_pg_called_up = True
        creditor.save(update_fields=["requires_pg_called_up"])
        try:
            result = assess_case(
                _m6_payload(
                    creditors=[
                        {
                            "creditor_name": creditor.creditor_name,
                            "balance": 5000.0,
                            "creditor_type": "loan",
                            "guarantee_called_up": False,
                        },
                        {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                    ],
                ),
                detected_representatives=set(),
            )
        finally:
            creditor.requires_pg_called_up = False
            creditor.save(update_fields=["requires_pg_called_up"])
        self.assertIn(
            "GUARANTOR-NOT-CALLED-UP",
            [r.rule_id for r in result["flags"]],
        )

    def test_build_phase7_serializes_module6_hard_blocks(self):
        """build_phase7_response_fields (ResultAggregator) must include Module 6 hard blocks."""
        result = assess_case(
            _m6_payload(
                is_police_officer=True,
                creditors=[
                    {"creditor_name": "No1 Copperpot CU", "balance": 1500.0, "creditor_type": "loan"},
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        serialized = build_phase7_response_fields(result)
        hard_ids = self._ids_in_bin(serialized, "hard_blocks")
        self.assertIn("SPECIAL-EMPLOYER-COPPERPOT", hard_ids)
        self.assertEqual(serialized["overall"], "blocked")
        self.assertFalse(serialized["passes_all_hard_blocks"])
        # Verify JSON-serializable (no Decimal / set leaking out)
        import json
        json.dumps(serialized)

    def test_build_phase7_serializes_module6_flags(self):
        """build_phase7_response_fields must include Module 6 flags (IE-MATCH-FAIL)."""
        bamboo = CreditorCriteria.objects.filter(creditor_name="Bamboo").first()
        self.assertIsNotNone(bamboo)
        CreditorOpenBankingRule.objects.update_or_create(
            creditor=bamboo,
            defaults={"ie_must_match_exactly": True, "review_period_months": 3},
        )
        result = assess_case(
            _m6_payload(
                creditors=[
                    {
                        "creditor_name": "Bamboo",
                        "balance": 3000.0,
                        "creditor_type": "loan",
                        "ie_matches_loan_application": False,
                    },
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        serialized = build_phase7_response_fields(result)
        flag_ids = self._ids_in_bin(serialized, "flags")
        self.assertIn("IE-MATCH-FAIL", flag_ids)

    def test_build_phase7_serializes_module6_info(self):
        """build_phase7_response_fields must include Module 6 info (PENNY-POST)."""
        result = assess_case(
            _m6_payload(
                is_royal_mail_employee=True,
                creditors=[
                    {"creditor_name": "Penny Post CU", "balance": 2000.0, "creditor_type": "loan"},
                    {"creditor_name": "Barclays", "balance": 10000.0, "creditor_type": "loan"},
                ],
            ),
            detected_representatives=set(),
        )
        serialized = build_phase7_response_fields(result)
        info_ids = self._ids_in_bin(serialized, "info")
        self.assertIn("SPECIAL-EMPLOYER-PENNY-POST", info_ids)
        import json
        json.dumps(serialized)
