"""
Phase 4 engine tests: VW termination, DMP reject, county council routing.
"""

from django.test import TestCase

from debt_app.criteria_engine import assess_case
from debt_app.models import CountyCouncilRouting, CreditorCriteria
from debt_app.tests.test_phase3 import _minimal_old_payload


def _phase4_base_payload(**overrides):
    """Passes TIG-01/02; minimal creditors/docs for non-VW integration paths."""
    payload = _minimal_old_payload()
    payload.update(overrides)
    return payload


def _rule_ids(blocks):
    return [r.rule_id for r in blocks]


class TestVehicleTerminationRisk(TestCase):
    def test_volkswagen_financial_services(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": "Volkswagen Financial Services",
                    "balance": 10000.00,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("PHASE4-VW-TERMINATION", _rule_ids(result["hard_blocks"]))

    def test_vwfs(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": "VWFS",
                    "balance": 10000.00,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("PHASE4-VW-TERMINATION", _rule_ids(result["hard_blocks"]))

    def test_audi_finance(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": "Audi Finance",
                    "balance": 10000.00,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("PHASE4-VW-TERMINATION", _rule_ids(result["hard_blocks"]))

    def test_non_vw_creditors_only(self):
        payload = _phase4_base_payload()
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-VW-TERMINATION", _rule_ids(result["hard_blocks"]))


class TestDmpStatus(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.commsave = CreditorCriteria.objects.filter(
            reject_if_in_dmp=True,
            creditor_name__icontains="Commsave",
        ).first()
        cls.non_dmp_creditor = (
            CreditorCriteria.objects.filter(reject_if_in_dmp=False)
            .exclude(creditor_name__icontains="Commsave")
            .exclude(creditor_name__icontains="CAMBRIAN")
            .first()
        )

    def test_dmp_true_commsave_blocks(self):
        self.assertIsNotNone(self.commsave)
        payload = _phase4_base_payload(
            is_currently_in_dmp=True,
            creditors=[
                {
                    "creditor_name": self.commsave.creditor_name,
                    "balance": 10000.00,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("PHASE4-DMP-REJECT", _rule_ids(result["hard_blocks"]))

    def test_dmp_true_non_dmp_creditor_no_block(self):
        self.assertIsNotNone(self.non_dmp_creditor)
        payload = _phase4_base_payload(
            is_currently_in_dmp=True,
            creditors=[
                {
                    "creditor_name": self.non_dmp_creditor.creditor_name,
                    "balance": 10000.00,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-DMP-REJECT", _rule_ids(result["hard_blocks"]))

    def test_dmp_false_commsave_no_block(self):
        self.assertIsNotNone(self.commsave)
        payload = _phase4_base_payload(
            is_currently_in_dmp=False,
            creditors=[
                {
                    "creditor_name": self.commsave.creditor_name,
                    "balance": 10000.00,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-DMP-REJECT", _rule_ids(result["hard_blocks"]))

    def test_commsave_trading_name_resolution(self):
        if not self.commsave or not self.commsave.trading_names:
            self.skipTest(
                "No Commsave trading name seeded; helper path covered by canonical name test."
            )
        trading_name = self.commsave.trading_names[0]
        payload = _phase4_base_payload(
            is_currently_in_dmp=True,
            creditors=[
                {
                    "creditor_name": trading_name,
                    "balance": 10000.00,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertIn("PHASE4-DMP-REJECT", _rule_ids(result["hard_blocks"]))


class TestCountyCouncilRouting(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buckinghamshire = "Buckinghamshire"
        cls.expected_districts = list(
            CountyCouncilRouting.objects.filter(
                county_name__iexact=cls.buckinghamshire
            ).values_list("district_name", flat=True)
        )

    def test_buckinghamshire_council_tax_flags(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": self.buckinghamshire,
                    "balance": 2000.00,
                    "creditor_type": "council tax",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        county_flags = [
            f for f in result["flags"] if f.rule_id == "PHASE4-COUNTY-COUNCIL"
        ]
        self.assertEqual(len(county_flags), 1)
        for district in self.expected_districts:
            self.assertIn(district, county_flags[0].message)

    def test_buckinghamshire_personal_loan_no_flag(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": self.buckinghamshire,
                    "balance": 2000.00,
                    "creditor_type": "personal loan",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-COUNTY-COUNCIL", _rule_ids(result["flags"]))

    def test_south_bucks_district_no_flag(self):
        payload = _phase4_base_payload(
            creditors=[
                {
                    "creditor_name": "South Bucks",
                    "balance": 2000.00,
                    "creditor_type": "council tax",
                },
                {
                    "creditor_name": "Barclays",
                    "balance": 8000.00,
                    "creditor_type": "loan",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-COUNTY-COUNCIL", _rule_ids(result["flags"]))

    def test_empty_creditor_list_no_error(self):
        payload = _phase4_base_payload(creditors=[])
        payload["crm_data"]["total_unsecured_debt"] = 0
        result = assess_case(payload, detected_representatives=set())
        self.assertNotIn("PHASE4-COUNTY-COUNCIL", _rule_ids(result["flags"]))
        self.assertEqual(result["overall"], "blocked")


class TestPhase4Integration(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.commsave = CreditorCriteria.objects.filter(
            reject_if_in_dmp=True,
            creditor_name__icontains="Commsave",
        ).first()

    def test_combined_vw_dmp_county(self):
        self.assertIsNotNone(self.commsave)
        payload = _phase4_base_payload(
            is_currently_in_dmp=True,
            creditors=[
                {
                    "creditor_name": "Volkswagen Financial Services",
                    "balance": 5000.00,
                    "creditor_type": "hire purchase",
                },
                {
                    "creditor_name": self.commsave.creditor_name,
                    "balance": 5000.00,
                    "creditor_type": "loan",
                },
                {
                    "creditor_name": "Buckinghamshire",
                    "balance": 2000.00,
                    "creditor_type": "council tax",
                },
            ],
        )
        result = assess_case(payload, detected_representatives=set())
        hard_ids = _rule_ids(result["hard_blocks"])
        flag_ids = _rule_ids(result["flags"])
        self.assertIn("PHASE4-VW-TERMINATION", hard_ids)
        self.assertIn("PHASE4-DMP-REJECT", hard_ids)
        self.assertIn("PHASE4-COUNTY-COUNCIL", flag_ids)

    def test_old_payload_still_valid(self):
        payload = _minimal_old_payload()
        result = assess_case(payload, detected_representatives=set())
        self.assertIn(result["overall"], ("blocked", "indeterminate", "flagged", "pass"))
        self.assertIsInstance(result["hard_blocks"], list)
        self.assertIsInstance(result["flags"], list)
        self.assertIn("recommended_solution", result)
