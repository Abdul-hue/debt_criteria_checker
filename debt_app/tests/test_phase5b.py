"""
Phase 5b tests: council sole reject, current-year CT info, Huntingdonshire triggers.
"""

from django.test import TestCase

from debt_app.criteria_engine import _check_council_rules, _parse_case
from debt_app.models import CouncilRule
from debt_app.tests.test_phase4 import _phase4_base_payload
import debt_app.criteria_engine as criteria_engine


def _phase5b_payload(**overrides):
    payload = _phase4_base_payload()
    payload.update(overrides)
    return payload


def _parsed(**overrides):
    return _parse_case(_phase5b_payload(**overrides))


def _findings_codes(positions, council_substr):
    pos = next(p for p in positions if council_substr in p["council_name"])
    return [f["code"] for f in pos["findings"]]


class TestShropshireRejectIfSole(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.shropshire = CouncilRule.objects.filter(
            council_name__icontains="Shropshire"
        ).first()

    def setUp(self):
        self.assertIsNotNone(self.shropshire)
        self.assertTrue(self.shropshire.reject_if_sole)

    def test_sole_account_hard_block(self):
        case = _parsed(
            has_partner_on_case=False,
            creditors=[
                {
                    "creditor_name": self.shropshire.council_name,
                    "balance": 500.0,
                    "creditor_type": "pcn",
                    "is_joint": False,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_council_rules(case)
        codes = _findings_codes(positions, "Shropshire")
        self.assertIn("COUNCIL-SOLE-REJECT", codes)
        pos = next(p for p in positions if "Shropshire" in p["council_name"])
        self.assertEqual(pos["effective_status"], "REJECT")

    def test_joint_one_party_pod_flag(self):
        case = _parsed(
            has_partner_on_case=False,
            creditors=[
                {
                    "creditor_name": self.shropshire.council_name,
                    "balance": 500.0,
                    "creditor_type": "pcn",
                    "is_joint": True,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        self.assertFalse(
            case["has_partner_on_case"],
            "Precondition failed: has_partner_on_case should be False for one-party test",
        )
        positions = _check_council_rules(case)
        codes = _findings_codes(positions, "Shropshire")
        self.assertIn("COUNCIL-SOLE-POD-ONLY", codes)
        self.assertNotIn("COUNCIL-SOLE-REJECT", codes)

    def test_joint_both_parties_no_sole_block(self):
        case = _parsed(
            has_partner_on_case=True,
            creditors=[
                {
                    "creditor_name": self.shropshire.council_name,
                    "balance": 500.0,
                    "creditor_type": "pcn",
                    "is_joint": True,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        self.assertTrue(
            case["has_partner_on_case"],
            "Precondition failed: has_partner_on_case should be True for both-parties test",
        )
        positions = _check_council_rules(case)
        codes = _findings_codes(positions, "Shropshire")
        self.assertNotIn("COUNCIL-SOLE-REJECT", codes)
        self.assertNotIn("COUNCIL-SOLE-POD-ONLY", codes)


class TestIncludeCurrentYearCt(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cardiff = CouncilRule.objects.filter(
            council_name__icontains="Cardiff Council"
        ).first()
        cls.walsall = CouncilRule.objects.filter(
            council_name__icontains="Walsall"
        ).first()

    def _assert_current_year_info(self, council_rule):
        self.assertIsNotNone(council_rule)
        self.assertTrue(council_rule.include_current_year_ct)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": council_rule.council_name,
                    "balance": 1200.0,
                    "creditor_type": "council tax",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_council_rules(case)
        codes = _findings_codes(positions, council_rule.council_name.split()[0])
        self.assertIn("INFO-INCLUDE-CURRENT-YEAR-CT", codes)

    def test_cardiff_include_current_year_ct(self):
        self._assert_current_year_info(self.cardiff)

    def test_walsall_include_current_year_ct(self):
        self._assert_current_year_info(self.walsall)


class TestHuntingdonshireTriggers(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.huntingdon = CouncilRule.objects.filter(
            council_name__icontains="Huntingdon"
        ).first()

    def setUp(self):
        self.assertIsNotNone(self.huntingdon)

    def _huntingdon_case(self, **case_overrides):
        creditors = case_overrides.pop("creditors", None)
        if creditors is None:
            creditors = [
                {
                    "creditor_name": self.huntingdon.council_name,
                    "balance": 1500.0,
                    "creditor_type": "council tax",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ]
        return _parsed(creditors=creditors, **case_overrides)

    def _hard_block_codes(self, case):
        positions = _check_council_rules(case)
        return _findings_codes(positions, "Huntingdon")

    def test_benefits_only_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(income_is_benefits_only=True),
        )
        self.assertIn("COUNCIL-TRIGGER-BENEFITS-ONLY", codes)

    def test_any_benefits_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(receives_any_benefits=True),
        )
        self.assertIn("COUNCIL-TRIGGER-ANY-BENEFITS", codes)

    def test_previous_iva_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(previous_iva=True),
        )
        self.assertIn("COUNCIL-TRIGGER-PREVIOUS-IVA", codes)

    def test_aoe_in_place_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(aoe_in_place=True),
        )
        self.assertIn("COUNCIL-TRIGGER-AOE-IN-PLACE", codes)

    def test_dro_criteria_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(dro_criteria_met=True),
        )
        self.assertIn("COUNCIL-TRIGGER-DRO-CRITERIA", codes)

    def test_joint_one_employed_hard_block(self):
        codes = self._hard_block_codes(
            self._huntingdon_case(is_joint_case=True, is_employed=True),
        )
        self.assertIn("COUNCIL-TRIGGER-JOINT-ONE-EMPLOYED", codes)

    def test_none_triggered_no_council_hard_blocks(self):
        codes = self._hard_block_codes(self._huntingdon_case())
        council_hard = [c for c in codes if c.startswith("COUNCIL-TRIGGER-")]
        self.assertEqual(council_hard, [])

    def test_no_pending_placeholder(self):
        case = self._huntingdon_case()
        positions = _check_council_rules(case)
        codes = _findings_codes(positions, "Huntingdon")
        self.assertNotIn("COUNCIL-TRIGGER-RULES-PENDING", codes)


class TestPhase5bEngineHygiene(TestCase):
    def test_no_blocked_reason_string_match_in_check_council_rules(self):
        import inspect
        source = inspect.getsource(criteria_engine._check_council_rules)
        self.assertNotIn("blocked_reason", source)
        self.assertNotIn("current ct year", source.lower())
