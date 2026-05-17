"""
Phase 5 engine tests: per-creditor and per-council evaluation.
"""

from django.test import TestCase

from debt_app.criteria_engine import (
    _check_council_rules,
    _check_creditor_individual,
    _parse_case,
    assess_case,
)
from debt_app.helpers import get_creditor_by_trading_name
from debt_app.models import (
    CouncilRule,
    CreditorCriteria,
    DebtTypeCouncilVote,
)
from debt_app.tests.test_phase3 import _minimal_old_payload
from debt_app.tests.test_phase4 import _phase4_base_payload


def _phase5_payload(**overrides):
    payload = _phase4_base_payload()
    payload.update(overrides)
    return payload


def _parsed(**overrides):
    return _parse_case(_phase5_payload(**overrides))


class TestCreditorIndividualChecker(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tbi = CreditorCriteria.objects.filter(
            blocked_until_cleared=True,
            creditor_name__icontains="TBI",
        ).first()
        cls.bamboo = CreditorCriteria.objects.filter(
            reject_if_never_made_payment=True,
            creditor_name__icontains="Bamboo",
        ).first()
        cls.moneybarn = CreditorCriteria.objects.filter(
            vehicle_arrears_repossession_months__isnull=False,
            creditor_name__icontains="Moneybarn",
        ).first()
        cls.commsave = CreditorCriteria.objects.filter(
            creditor_name__icontains="Commsave",
        ).first()

    def test_unknown_creditor_unknown_status(self):
        case = _parsed(
            creditors=[
                {
                    "creditor_name": "Totally Unknown Lender XYZ",
                    "balance": 1000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_creditor_individual(case)
        unknown = next(
            p for p in positions
            if p["creditor_name"] == "Totally Unknown Lender XYZ"
        )
        self.assertEqual(unknown["effective_status"], "UNKNOWN")
        self.assertIn("No criteria row for this creditor", unknown["findings"][0]["reason"])

    def test_tbi_blocked_until_cleared(self):
        self.assertIsNotNone(self.tbi)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.tbi.creditor_name,
                    "balance": 5000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_creditor_individual(case)
        tbi_pos = next(p for p in positions if p["resolved_canonical_name"] == self.tbi.creditor_name)
        self.assertEqual(tbi_pos["effective_status"], "REJECT")
        codes = [f["code"] for f in tbi_pos["findings"]]
        self.assertIn("CREDITOR-BLOCKED", codes)

    def test_bamboo_no_payment_hard_block(self):
        self.assertIsNotNone(self.bamboo)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.bamboo.creditor_name,
                    "balance": 3000.0,
                    "creditor_type": "loan",
                    "first_payment_made": False,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_creditor_individual(case)
        bamboo_pos = next(
            p for p in positions if p["resolved_canonical_name"] == self.bamboo.creditor_name
        )
        self.assertEqual(bamboo_pos["effective_status"], "REJECT")
        self.assertTrue(
            any(f["code"] == "CREDITOR-NO-PAYMENT" for f in bamboo_pos["findings"])
        )

    def test_bamboo_payment_made_no_never_payment_block(self):
        self.assertIsNotNone(self.bamboo)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.bamboo.creditor_name,
                    "balance": 3000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_creditor_individual(case)
        bamboo_pos = next(
            p for p in positions if p["resolved_canonical_name"] == self.bamboo.creditor_name
        )
        self.assertNotIn(
            "CREDITOR-NO-PAYMENT",
            [f["code"] for f in bamboo_pos["findings"]],
        )

    def test_commsave_cu_trading_name(self):
        self.assertIsNotNone(self.commsave)
        row = get_creditor_by_trading_name("Commsave CU")
        self.assertEqual(row.creditor_name, self.commsave.creditor_name)

    def test_moneybarn_vehicle_arrears_flag(self):
        self.assertIsNotNone(self.moneybarn)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.moneybarn.creditor_name,
                    "balance": 8000.0,
                    "creditor_type": "hire purchase",
                    "vehicle_arrears_months": 3,
                    "client_still_has_asset_in_possession": True,
                    "arrangement_confirmed_before_proposing": False,
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_creditor_individual(case)
        mb = next(
            p for p in positions if p["resolved_canonical_name"] == self.moneybarn.creditor_name
        )
        codes = [f["code"] for f in mb["findings"]]
        self.assertIn("CREDITOR-REPOSSESSION-RISK", codes)
        self.assertIn("CREDITOR-ARRANGEMENT-CALL", codes)
        self.assertIn("CREDITOR-FEES-CAP", codes)
        self.assertGreaterEqual(len(codes), 3)


class TestCouncilRulesChecker(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.southwark = CouncilRule.objects.filter(
            council_name__icontains="Southwark"
        ).first()
        cls.mid_suffolk = CouncilRule.objects.filter(
            council_name__icontains="Mid Suffolk"
        ).first()
        cls.colchester = CouncilRule.objects.filter(
            council_name__icontains="Colchester"
        ).first()
        cls.slough = CouncilRule.objects.filter(
            council_name__icontains="Slough"
        ).first()

    def test_buckinghamshire_county_skipped(self):
        case = _parsed(
            creditors=[
                {
                    "creditor_name": "Buckinghamshire",
                    "balance": 2000.0,
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
        self.assertEqual(positions, [])

    def test_southwark_pcn_accept(self):
        self.assertIsNotNone(self.southwark)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.southwark.council_name,
                    "balance": 500.0,
                    "creditor_type": "pcn",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.0,
                    "creditor_type": "loan",
                },
            ],
        )
        positions = _check_council_rules(case)
        sw = next(p for p in positions if "Southwark" in p["council_name"])
        self.assertEqual(sw["effective_status"], "ACCEPT")

    def test_southwark_council_tax_reject(self):
        self.assertIsNotNone(self.southwark)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.southwark.council_name,
                    "balance": 2000.0,
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
        sw = next(p for p in positions if "Southwark" in p["council_name"])
        self.assertEqual(sw["effective_status"], "REJECT")

    def test_mid_suffolk_employed_reject(self):
        self.assertIsNotNone(self.mid_suffolk)
        case = _parsed(
            is_employed=True,
            creditors=[
                {
                    "creditor_name": self.mid_suffolk.council_name,
                    "balance": 1500.0,
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
        ms = next(p for p in positions if "Mid Suffolk" in p["council_name"])
        self.assertEqual(ms["effective_status"], "REJECT")

    def test_mid_suffolk_unemployed_accept(self):
        self.assertIsNotNone(self.mid_suffolk)
        case = _parsed(
            is_employed=False,
            creditors=[
                {
                    "creditor_name": self.mid_suffolk.council_name,
                    "balance": 1500.0,
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
        ms = next(p for p in positions if "Mid Suffolk" in p["council_name"])
        self.assertEqual(ms["effective_status"], "ACCEPT")

    def test_mid_suffolk_ignores_dtcv_if_present(self):
        self.assertIsNotNone(self.mid_suffolk)
        dtcv_count = DebtTypeCouncilVote.objects.filter(
            council=self.mid_suffolk
        ).count()
        case = _parsed(
            is_employed=False,
            creditors=[
                {
                    "creditor_name": self.mid_suffolk.council_name,
                    "balance": 1500.0,
                    "creditor_type": "council tax",
                },
            ],
        )
        positions = _check_council_rules(case)
        ms = next(p for p in positions if "Mid Suffolk" in p["council_name"])
        self.assertEqual(ms["effective_status"], "ACCEPT")
        self.assertEqual(dtcv_count, 0)

    def test_colchester_min_dividend_info(self):
        self.assertIsNotNone(self.colchester)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.colchester.council_name,
                    "balance": 2000.0,
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
        col = next(p for p in positions if "Colchester" in p["council_name"])
        reasons = " ".join(f["reason"] for f in col["findings"])
        self.assertIn("45", reasons)

    def test_slough_do_not_chase(self):
        self.assertIsNotNone(self.slough)
        case = _parsed(
            creditors=[
                {
                    "creditor_name": self.slough.council_name,
                    "balance": 1000.0,
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
        sl = next(p for p in positions if "Slough" in p["council_name"])
        self.assertTrue(
            any("do not chase" in f["reason"].lower() for f in sl["findings"])
        )


class TestPhase5Prereqs(TestCase):
    def test_commsave_trading_name_after_migration(self):
        row = get_creditor_by_trading_name("Commsave CU")
        self.assertIn("Commsave", row.creditor_name)

    def test_cambrian_trading_name(self):
        row = get_creditor_by_trading_name("Cambrian CU")
        self.assertIn("CAMBRIAN", row.creditor_name.upper())

    def test_creditor_count_at_least_phase2_plus_legacy(self):
        self.assertGreaterEqual(CreditorCriteria.objects.count(), 100)


class TestPhase5Integration(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.commsave = CreditorCriteria.objects.filter(
            creditor_name__icontains="Commsave",
        ).first()
        cls.moneybarn = CreditorCriteria.objects.filter(
            creditor_name__icontains="Moneybarn",
        ).first()

    def test_combined_case_positions(self):
        self.assertIsNotNone(self.commsave)
        self.assertIsNotNone(self.moneybarn)
        payload = _phase5_payload(
            creditors=[
                {
                    "creditor_name": "Volkswagen Financial Services",
                    "balance": 5000.0,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Commsave CU",
                    "balance": 4000.0,
                    "creditor_type": "loan",
                    "first_payment_made": True,
                },
                {
                    "creditor_name": "Buckinghamshire",
                    "balance": 2000.0,
                    "creditor_type": "council tax",
                },
                {
                    "creditor_name": self.moneybarn.creditor_name,
                    "balance": 6000.0,
                    "creditor_type": "hire purchase",
                    "vehicle_arrears_months": 3,
                    "client_still_has_asset_in_possession": True,
                    "arrangement_confirmed_before_proposing": True,
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("creditor_positions", result)
        self.assertIn("council_positions", result)
        canon = {p["resolved_canonical_name"] for p in result["creditor_positions"]}
        self.assertIn(self.commsave.creditor_name, canon)
        self.assertIn(self.moneybarn.creditor_name, canon)
        mb = next(
            p for p in result["creditor_positions"]
            if p["resolved_canonical_name"] == self.moneybarn.creditor_name
        )
        self.assertTrue(
            any(f["code"] == "CREDITOR-REPOSSESSION-RISK" for f in mb["findings"])
        )
        buck = [p for p in result["council_positions"] if "Buckinghamshire" in p.get("council_name", "")]
        self.assertEqual(buck, [])

    def test_old_payload_empty_position_lists(self):
        result = assess_case(_minimal_old_payload(), detected_representatives=set())
        self.assertEqual(result["creditor_positions"], [])
        self.assertEqual(result["council_positions"], [])
